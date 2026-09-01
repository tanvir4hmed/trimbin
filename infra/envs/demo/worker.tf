/**
 * The ingest worker.
 *
 * Same image as the API, different command. ffmpeg, the measurement code and
 * the ClickHouse client are already in that image, and a second Dockerfile
 * would be a second copy of the same dependency list to keep in step — which
 * would drift, and the drift would show up as a worker measuring differently
 * from the eval harness.
 *
 * A push subscription rather than a pull loop. Pull would hold an instance open
 * all night waiting for a morning upload that may never come; push starts an
 * instance when a clip arrives and stops it when the queue drains.
 */

resource "google_service_account" "worker" {
  account_id   = "${local.name}-worker"
  display_name = "Trimbin ingest worker"
}

# Read the source, write the proxy. Not objectAdmin on originals: the worker has
# no reason to delete a customer's footage, and the narrower grant means a bug
# in ffmpeg handling cannot become data loss.
resource "google_storage_bucket_iam_member" "worker_originals" {
  bucket = google_storage_bucket.originals.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_storage_bucket_iam_member" "worker_proxies" {
  bucket = google_storage_bucket.proxies.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_secret_manager_secret_iam_member" "worker_clickhouse" {
  secret_id = google_secret_manager_secret.clickhouse_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.worker.email}"
}

# Firestore for job progress, and Vertex for model calls. Publishing is granted
# separately on the one ingest topic below; a project-wide publisher role would
# let a compromised worker address unrelated topics it never needs.
resource "google_project_iam_member" "worker_roles" {
  for_each = toset([
    "roles/datastore.user",
    "roles/aiplatform.user",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.worker.email}"
}

# Ingest completion schedules an independent full-take analysis message. This
# separation matters: a model timeout retries analysis only, never the clip's
# proxy encode or ClickHouse ingest row.
resource "google_pubsub_topic_iam_member" "worker_analysis_publisher" {
  topic  = google_pubsub_topic.ingest.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_cloud_run_v2_service" "worker" {
  name     = "${local.name}-worker"
  location = var.region
  labels   = local.labels

  deletion_protection = false

  template {
    service_account = google_service_account.worker.email

    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    # One clip per instance. ffmpeg saturates a core, so a second concurrent
    # encode does not double throughput — it halves the speed of both and pushes
    # each closer to the acknowledgement deadline, where Pub/Sub redelivers work
    # that was nearly finished.
    max_instance_request_concurrency = 1

    # Matches ack_deadline_seconds on the subscription. If they disagree, the
    # shorter one wins silently: Pub/Sub redelivers a clip that is still being
    # encoded, and two instances do the same work.
    timeout = "600s"

    containers {
      # Replaced by CI, exactly as with the API. See the comment there.
      image = "us-docker.pkg.dev/cloudrun/container/hello"

      # The command that makes this a worker rather than a second API is set by
      # CI, not here, and for the same reason the image is: this service is
      # first created against Google's placeholder, and that image has no
      # uvicorn in it. Declaring the override here fails the startup probe on
      # every first apply, with an error that says the container failed to start
      # and does not say why.
      #
      # It lives in the deploy workflow beside the image it belongs to.

      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
        # Two cores because this is the one part of the system that is genuinely
        # compute-bound, and because halving the encode time more than halves
        # the risk of hitting the ack deadline on a long take.
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
      env {
        name = "TRIMBIN_CLICKHOUSE_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.clickhouse_password.secret_id
            version = "latest"
          }
        }
      }

      # The worker does not search, but it shares this image with the API and a
      # container that cannot start because half its configuration is missing is
      # a worse failure than an unused variable.
      env {
        name  = "TRIMBIN_CLICKHOUSE_READER_USER"
        value = "trimbin_reader"
      }

      startup_probe {
        http_get {
          path = "/health"
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 10
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      template[0].containers[0].command,
      template[0].containers[0].args,
      client,
      client_version,
    ]
  }
}

# ---------------------------------------------------------------------------
# Who may call it.
#
# Note what is absent: no allUsers binding. The worker acts on whatever clip id
# it is handed, so an open endpoint would let a stranger make us re-encode
# arbitrary footage at our expense. Cloud Run rejects unauthenticated callers
# before the container starts, which is why worker/main.py verifies nothing
# itself.
# ---------------------------------------------------------------------------

resource "google_service_account" "pubsub_push" {
  account_id   = "${local.name}-push"
  display_name = "Pub/Sub push identity"
}

resource "google_cloud_run_v2_service_iam_member" "worker_invoker" {
  name     = google_cloud_run_v2_service.worker.name
  location = google_cloud_run_v2_service.worker.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_push.email}"
}

# Pub/Sub signs the OIDC token as this account, so its own service agent needs
# permission to mint tokens for it. Without this the subscription is created
# successfully and every delivery fails with 403 — a failure that looks like a
# worker bug and is not.
data "google_project" "current" {
  project_id = var.project_id
}

resource "google_service_account_iam_member" "pubsub_mints_tokens" {
  service_account_id = google_service_account.pubsub_push.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

# The dead letter topic only holds messages if Pub/Sub is allowed to move them
# there and to acknowledge the originals.
resource "google_pubsub_topic_iam_member" "dead_letter_publisher" {
  topic  = google_pubsub_topic.dead_letter.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription_iam_member" "dead_letter_subscriber" {
  subscription = google_pubsub_subscription.ingest.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}
