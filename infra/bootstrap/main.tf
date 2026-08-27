/**
 * Bootstrap — the one configuration applied by hand.
 *
 * Terraform cannot create the bucket that holds its own state, so this runs once,
 * locally, before anything else. It is still Terraform: no resource in this
 * project is ever created by clicking in a console.
 *
 * It also establishes Workload Identity Federation, which is how CI authenticates
 * without a service account key. No long-lived credential ever exists on disk or
 * in GitHub — the only thing stored there is a resource name, which is useless
 * without the repository binding below.
 *
 *   cd infra/bootstrap
 *   terraform init && terraform apply
 *
 * Copy the outputs into GitHub repository secrets. Everything after this is
 * driven by `git push`.
 */

terraform {
  required_version = ">= 1.9"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ---------------------------------------------------------------------------
# APIs. Enabled here because everything downstream depends on them existing.
# ---------------------------------------------------------------------------

resource "google_project_service" "required" {
  for_each = toset([
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudtrace.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "sts.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false # other things may depend on these
}

# ---------------------------------------------------------------------------
# Terraform state.
# ---------------------------------------------------------------------------

resource "google_storage_bucket" "tfstate" {
  name     = "${var.project_id}-tfstate"
  location = var.region

  # State history is the only record of what infrastructure used to look like.
  versioning { enabled = true }

  # A bucket holding state must never be deletable by accident.
  force_destroy               = false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  lifecycle {
    prevent_destroy = true
  }
}

# ---------------------------------------------------------------------------
# Workload Identity Federation — CI authenticates as itself, not as a key.
# ---------------------------------------------------------------------------

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions"
  description               = "Keyless authentication for CI"

  depends_on = [google_project_service.required]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # Without this, any GitHub repository in the world could assume this identity.
  attribute_condition = "assertion.repository == '${var.github_repository}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  account_id   = "trimbin-deployer"
  display_name = "Trimbin CI deployer"
  description  = "Assumed by GitHub Actions via Workload Identity Federation"
}

resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

# Broad while the shape of the infrastructure is still settling. Narrowed to the
# specific roles actually exercised once Phase 1 has run end to end.
resource "google_project_iam_member" "deployer_roles" {
  for_each = toset([
    "roles/editor",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountUser",
    "roles/resourcemanager.projectIamAdmin",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# ---------------------------------------------------------------------------
# A runaway agent should cost an alert, not a month of credits.
# ---------------------------------------------------------------------------

resource "google_billing_budget" "guard" {
  count = var.billing_account_id == "" ? 0 : 1

  billing_account = var.billing_account_id
  display_name    = "trimbin-budget-guard"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_usd)
    }
  }

  dynamic "threshold_rules" {
    for_each = [0.5, 0.8, 1.0]
    content {
      threshold_percent = threshold_rules.value
    }
  }
}

data "google_project" "this" {
  project_id = var.project_id
}
