/**
 * The sandbox sweep.
 *
 * A visitor's footage is theirs. Keeping it because deleting is work would be
 * the wrong default for material somebody uploaded to try a demo, so it is
 * removed after a day — objects and rows together, since a row pointing at a
 * deleted object is an archive claiming a clip it cannot play.
 *
 * Cloud Scheduler rather than a cron inside the service. The API scales to zero
 * and a process that must run at 3am cannot live inside one that may not exist
 * at 3am.
 */

resource "google_service_account" "scheduler" {
  account_id   = "${local.name}-scheduler"
  display_name = "Trimbin scheduled maintenance"
}

# The only caller of /maintenance/*. The route is not public, and this is what
# makes that true: Cloud Run checks the token before the container sees the
# request, so authorisation does not depend on the application remembering to.
resource "google_cloud_run_v2_service_iam_member" "scheduler_invokes_api" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_scheduler_job" "sandbox_retention" {
  name        = "${local.name}-sandbox-retention"
  description = "Delete visitor footage older than the sandbox retention window."
  region      = var.region

  # Hourly, not daily. The retention window is measured in hours, so a daily
  # sweep would keep some clips for nearly twice as long as promised — and a
  # promise about somebody's footage is not one to round off.
  schedule  = "17 * * * *"
  time_zone = "UTC"

  # Deleting is idempotent and the next run is an hour away, so a failed attempt
  # is better left to the schedule than retried against a service that may be
  # having a bad minute.
  retry_config {
    retry_count = 1
  }

  http_target {
    # Through the load balancer, like every other caller. The service's own
    # generated URL cannot be referenced from inside its own definition, and
    # routing maintenance differently from everything else would mean one more
    # path that is only exercised at 3am.
    uri         = "https://${var.domain}/api/maintenance/sandbox-retention"
    http_method = "POST"

    # A body, so the request carries a Content-Length. The load balancer
    # answers a POST without one with a 411 before it reaches the service, and
    # that failure looks like the route being broken rather than the request
    # being malformed.
    headers = {
      "Content-Type" = "application/json"
    }
    body = base64encode("{}")

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = "https://${var.domain}"
    }
  }
}

# The API deletes sandbox objects on that schedule, so objectAdmin on the
# originals bucket is now load-bearing rather than incidental. Named here beside
# the thing that needs it; the grant itself is in run.tf with the others.
