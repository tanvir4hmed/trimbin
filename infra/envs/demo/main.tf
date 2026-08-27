/**
 * Demo environment — the deployment judges and the public will see.
 *
 * Everything here is created by CI on push to main. Nothing in this project is
 * ever created by clicking in a console, which is what makes the destroy path
 * trustworthy: if Terraform did not make it, Terraform cannot clean it up, and
 * something will quietly bill for a month after the demo ends.
 *
 * Cost shape matters here. The GenAI credit covers Gemini calls; infrastructure
 * comes out of a much smaller pool, so every resource below either scales to
 * zero or is chosen for being cheap at rest.
 */

terraform {
  required_version = ">= 1.9"

  backend "gcs" {
    # bucket and prefix supplied by CI via -backend-config
  }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    clickhouse = {
      source  = "ClickHouse/clickhouse"
      version = "~> 3.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "clickhouse" {
  organization_id = var.clickhouse_org_id
  token_key       = var.clickhouse_token_key
  token_secret    = var.clickhouse_token_secret
}

locals {
  name = "trimbin"

  labels = {
    app        = "trimbin"
    env        = "demo"
    managed-by = "terraform"
  }
}

# ---------------------------------------------------------------------------
# Media storage.
#
# Three buckets rather than one, because they have genuinely different lifecycles:
# originals are precious and cold, proxies are disposable and hot, and sprites are
# tiny and hot. A single bucket would force the same storage class and the same
# retention on all three.
# ---------------------------------------------------------------------------

resource "google_storage_bucket" "originals" {
  name                        = "${var.project_id}-originals"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = local.labels

  # Originals are read once, to make a proxy, and then almost never again.
  lifecycle_rule {
    condition { age = 30 }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  # Browsers upload straight here with a signed URL — video never passes through
  # the API, which keeps Cloud Run small and the egress bill honest.
  cors {
    origin          = var.allowed_origins
    method          = ["GET", "PUT", "HEAD"]
    response_header = ["Content-Type", "x-goog-resumable"]
    max_age_seconds = 3600
  }

  force_destroy = true # demo environment; teardown must actually work
}

resource "google_storage_bucket" "proxies" {
  name                        = "${var.project_id}-proxies"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "inherited" # served through the CDN
  labels                      = local.labels
  force_destroy               = true
}

resource "google_storage_bucket" "artifacts" {
  name                        = "${var.project_id}-artifacts"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = local.labels
  force_destroy               = true
}

# ---------------------------------------------------------------------------
# The public address.
#
# Reserved early and deliberately: DNS propagation is the one thing in this
# project that cannot be hurried, so the record is set on day one rather than on
# the day of the demo.
# ---------------------------------------------------------------------------

resource "google_compute_global_address" "ingress" {
  name        = "${local.name}-ingress"
  description = "Static IP for trimbin.qlitch.com"
}

# ---------------------------------------------------------------------------
# Firestore — the whiteboard.
#
# Projects, membership, job progress and director notes. All of it changes
# constantly and none of it has history worth keeping, which is exactly what
# ClickHouse is bad at and this is good at.
# ---------------------------------------------------------------------------

resource "google_firestore_database" "main" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  # Demo data is reproducible from seed; paying for point-in-time recovery on it
  # would be spending the scarce credit on the wrong thing.
  point_in_time_recovery_enablement = "POINT_IN_TIME_RECOVERY_DISABLED"
  delete_protection_state           = "DELETE_PROTECTION_DISABLED"
}

# ---------------------------------------------------------------------------
# ClickHouse — the logbook.
# ---------------------------------------------------------------------------

# The plaintext password exists in state, which is unavoidable for a generated
# credential — so state lives in a private, versioned bucket and the service
# itself only ever receives the hash.
resource "random_password" "clickhouse" {
  length      = 32
  special     = true
  min_upper   = 2
  min_lower   = 2
  min_numeric = 2
  min_special = 2
}

resource "clickhouse_service" "main" {
  name           = "${local.name}-demo"
  cloud_provider = "gcp"
  region         = var.clickhouse_region
  tier           = "development"

  password_hash = base64sha256(random_password.clickhouse.result)

  # Open during the build. Narrowed to Cloud Run's egress range before the demo
  # goes public — noted here so it is a scheduled task, not a forgotten one.
  ip_access = [{
    source      = "0.0.0.0/0"
    description = "open during build; restrict before public demo"
  }]

  # Development tier fixes its own resources, which suits this workload: the demo
  # is bursty — quiet for hours, then a judge arrives — and the tier idles on its
  # own. Paying to keep memory warm would spend the scarce credit on latency
  # nobody is waiting on.
}

resource "google_secret_manager_secret" "clickhouse_password" {
  secret_id = "${local.name}-clickhouse-password"
  labels    = local.labels

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "clickhouse_password" {
  secret      = google_secret_manager_secret.clickhouse_password.id
  secret_data = random_password.clickhouse.result
}

# ---------------------------------------------------------------------------
# Pub/Sub — the workflow spine.
#
# A shoot day is 200 clips and an hour of work with failures in the middle.
# Agents answer questions; they are the wrong shape for driving that. This is.
# ---------------------------------------------------------------------------

resource "google_pubsub_topic" "ingest" {
  name   = "${local.name}-ingest"
  labels = local.labels
}

resource "google_pubsub_topic" "dead_letter" {
  name   = "${local.name}-ingest-dead-letter"
  labels = local.labels
}

resource "google_pubsub_subscription" "ingest" {
  name   = "${local.name}-ingest-worker"
  topic  = google_pubsub_topic.ingest.id
  labels = local.labels

  # Long enough for ffmpeg to finish a proxy on a long take.
  ack_deadline_seconds = 600

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  # Five failures means the clip has a real problem. Parking it keeps the batch
  # moving and leaves evidence, instead of retrying forever and burning credit
  # on footage that will never process.
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }
}

# ---------------------------------------------------------------------------
# Container images.
# ---------------------------------------------------------------------------

resource "google_artifact_registry_repository" "images" {
  repository_id = local.name
  location      = var.region
  format        = "DOCKER"
  labels        = local.labels

  # Untagged layers accumulate on every build and nobody ever cleans them up.
  cleanup_policies {
    id     = "untagged"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s" # 7 days
    }
  }
}
