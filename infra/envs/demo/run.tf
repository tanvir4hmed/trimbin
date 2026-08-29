/**
 * Cloud Run, and the address in front of it.
 *
 * Sized for a demo: scales to zero, one CPU, and concurrency high enough that a
 * hundred simultaneous visitors land on two instances rather than a hundred.
 * The infrastructure credit here is small and the video egress is the part worth
 * protecting, so everything else is kept deliberately modest.
 */

# ---------------------------------------------------------------------------
# Identity.
#
# One service account per component with only the grants it uses. A single
# shared identity would mean a compromised web container could read the
# originals bucket, which it never touches.
# ---------------------------------------------------------------------------

resource "google_service_account" "api" {
  account_id   = "${local.name}-api"
  display_name = "Trimbin API"
}

resource "google_service_account" "web" {
  account_id   = "${local.name}-web"
  display_name = "Trimbin web"
}

resource "google_storage_bucket_iam_member" "api_originals" {
  bucket = google_storage_bucket.originals.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api.email}"
}

resource "google_storage_bucket_iam_member" "api_proxies" {
  bucket = google_storage_bucket.proxies.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api.email}"
}

resource "google_storage_bucket_iam_member" "api_artifacts" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "api_clickhouse" {
  secret_id = google_secret_manager_secret.clickhouse_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

# Signing an upload URL is a private key operation, and Cloud Run instances have
# no private key — the metadata server issues tokens and keeps the key. So the
# API asks IAM to sign as itself, which requires exactly this grant. Without it
# every upload request returns a 500 that says only "you need a private key",
# and no amount of local testing reproduces it: a developer machine has a key
# file and an instance never does.
resource "google_service_account_iam_member" "api_signs_as_itself" {
  service_account_id = google_service_account.api.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_roles" {
  for_each = toset([
    "roles/aiplatform.user",   # Gemini, for the agents
    "roles/datastore.user",    # Firestore
    "roles/pubsub.publisher",  # queue ingest work
    "roles/pubsub.subscriber", # and consume it
    "roles/cloudtrace.agent",  # per-agent spans, shown in the demo
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.api.email}"
}

# ---------------------------------------------------------------------------
# Services.
# ---------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "api" {
  name     = "${local.name}-api"
  location = var.region
  labels   = local.labels

  deletion_protection = false # demo environment; teardown must work

  template {
    service_account = google_service_account.api.email

    scaling {
      # Zero when nobody is looking. The demo is quiet for hours at a time and
      # a warm instance would spend the credit on latency nobody is waiting on.
      min_instance_count = 0
      max_instance_count = 4
    }

    # An async service waiting on a database most of the time. Eighty concurrent
    # requests per instance means a hundred visitors need two instances, not a
    # hundred.
    max_instance_request_concurrency = 80

    # Long enough for ffmpeg on a long take. Ingest runs in the worker, not in a
    # request, but a synchronous probe still has to finish.
    timeout = "600s"

    containers {
      # A placeholder, and deliberately so.
      #
      # Terraform creates the service before CI has built anything, so naming
      # the real image here makes the first apply fail on an image that cannot
      # exist yet — and every subsequent apply fight the tag CI just deployed.
      # The service is created against Google's hello image and immediately
      # replaced by `gcloud run deploy`; `ignore_changes` below keeps Terraform
      # from reverting it afterwards.
      image = "us-docker.pkg.dev/cloudrun/container/hello"

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
        # CPU only while a request is in flight. The alternative bills for idle
        # time on a service that is idle most of the day.
        cpu_idle          = true
        startup_cpu_boost = true
      }

      env {
        name  = "TRIMBIN_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "TRIMBIN_REGION"
        value = var.region
      }
      env {
        name  = "TRIMBIN_CLICKHOUSE_HOST"
        value = clickhouse_service.main.endpoints.https.host
      }
      env {
        name  = "TRIMBIN_CLICKHOUSE_PORT"
        value = tostring(clickhouse_service.main.endpoints.https.port)
      }
      env {
        name  = "TRIMBIN_ORIGINALS_BUCKET"
        value = google_storage_bucket.originals.name
      }
      env {
        name  = "TRIMBIN_PROXIES_BUCKET"
        value = google_storage_bucket.proxies.name
      }
      env {
        name  = "TRIMBIN_CDN_BASE_URL"
        value = "https://${var.domain}/media"
      }

      # Which application a sign-in token has to have been minted for. Empty
      # until the console step in docs/oauth-client.md is done, and while it is
      # empty the API rejects every bearer token — see auth.py for why that is
      # the safe direction to fail.
      env {
        name  = "TRIMBIN_OAUTH_CLIENT_ID"
        value = var.oauth_client_id
      }

      # Who may call /maintenance/*. This service is public, so Cloud Run lets
      # everyone reach those paths and the application is the only thing that
      # can tell the scheduler from a stranger.
      env {
        name  = "TRIMBIN_SCHEDULER_SERVICE_ACCOUNT"
        value = google_service_account.scheduler.email
      }
      # The domain, not the service's own URL. Referencing
      # google_cloud_run_v2_service.api.uri from inside the api service is a
      # cycle Terraform refuses, and the scheduler calls through the load
      # balancer anyway — so both sides derive this from var.domain and neither
      # has to know the other's generated address.
      env {
        name  = "TRIMBIN_SCHEDULER_AUDIENCE"
        value = "https://${var.domain}"
      }

      # Injected at start, never baked into the image and never in an env file
      # on disk.
      env {
        name = "TRIMBIN_CLICKHOUSE_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.clickhouse_password.secret_id
            version = "latest"
          }
        }
      }

      # The credentials MCP connects with. A separate user with SELECT and
      # nothing else, so a statement a model wrote cannot do anything a reader
      # could not — enforced by the server rather than by a pattern match.
      env {
        name  = "TRIMBIN_CLICKHOUSE_READER_USER"
        value = "trimbin_reader"
      }
      env {
        name = "TRIMBIN_CLICKHOUSE_READER_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.clickhouse_reader_password.secret_id
            version = "latest"
          }
        }
      }

      # Liveness only, and deliberately not touching the database: a check that
      # fails when a dependency is slow takes the service down for a problem it
      # could have survived.
      startup_probe {
        http_get {
          path = "/public/health"
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 10
      }
    }
  }

  lifecycle {
    # CI pushes new images and updates the revision. Terraform should not fight
    # it by reverting to whatever tag it last recorded.
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
}

# Public. The demo project and the accuracy page are both meant to
# be reachable without an account, and authorisation is enforced per route.
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service" "web" {
  name     = "${local.name}-web"
  location = var.region
  labels   = local.labels

  deletion_protection = false

  template {
    service_account = google_service_account.web.email

    scaling {
      min_instance_count = 0
      max_instance_count = 4
    }

    max_instance_request_concurrency = 80
    timeout                          = "60s"

    containers {
      # Placeholder for the same reason as the API: Terraform runs before CI has
      # built anything, and naming the real tag here creates a cycle it can never
      # resolve. Replaced immediately by `gcloud run deploy`.
      image = "us-docker.pkg.dev/cloudrun/container/hello"

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      # Next forwards API calls server-side, so the browser only ever talks to
      # one origin. No CORS preflight on every request, and the API's address is
      # not baked into client code where changing it would mean a rebuild.
      env {
        name  = "API_URL"
        value = google_cloud_run_v2_service.api.uri
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
}

resource "google_cloud_run_v2_service_iam_member" "web_public" {
  name     = google_cloud_run_v2_service.web.name
  location = google_cloud_run_v2_service.web.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
