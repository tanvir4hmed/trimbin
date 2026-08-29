/**
 * The second way in.
 *
 * Google Sign-In needs an OAuth client, and an OAuth client is the one thing in
 * this whole system that no API can create — it is a form in a console, which
 * is why docs/oauth-client.md exists. This deployment ran for a week with every
 * screen behind a door nobody could open: the dashboard, the queue, overrides,
 * comments, guest projects. All built, none reachable.
 *
 * So the API can also mint sessions of its own, and everything it needs to do
 * that is generated here. Nothing about this is manual and nothing about it is
 * checked into git.
 *
 * Read the codes after a deploy with:
 *
 *   gcloud secrets versions access latest --secret=trimbin-guest-pass
 *   gcloud secrets versions access latest --secret=trimbin-team-passes
 */

# What session tokens are signed with. Rotating it signs everybody out, which is
# the correct behaviour and the reason it is generated rather than configured:
# a signing key somebody chose is a signing key somebody can remember.
resource "random_password" "session_secret" {
  length  = 64
  special = false
}

resource "google_secret_manager_secret" "session_secret" {
  secret_id = "${local.name}-session-secret"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "session_secret" {
  secret      = google_secret_manager_secret.session_secret.id
  secret_data = random_password.session_secret.result
}

# The guest pass. One code, meant to be handed out — to a judge, in a
# submission, to anyone we want looking at this.
#
# It is safe to share because of what a guest can do rather than because of who
# holds it: every guest action is additive, attributed and reversible, and a
# guest cannot put footage into our productions. Long and random anyway, because
# a short code invites the guessing this is not built to withstand.
resource "random_password" "guest_pass" {
  length  = 20
  special = false
}

resource "google_secret_manager_secret" "guest_pass" {
  secret_id = "${local.name}-guest-pass"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "guest_pass" {
  secret      = google_secret_manager_secret.guest_pass.id
  secret_data = random_password.guest_pass.result
}

# One code per editor, so the archive records who actually decided something.
#
# A single shared team code would have been three lines shorter and would have
# made every override in this system say "one of the three of us" — which is
# precisely the attribution the archive exists to keep. The whole argument here
# is that a decision is worth what its attribution is worth.
resource "random_password" "team_pass" {
  for_each = toset(var.editor_emails)

  length  = 16
  special = false
}

resource "google_secret_manager_secret" "team_passes" {
  secret_id = "${local.name}-team-passes"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "team_passes" {
  secret = google_secret_manager_secret.team_passes.id
  # `email:code` pairs, comma separated — parsed on a sign-in attempt and never
  # cached, so a rotated code stops working immediately rather than when the
  # instance is next replaced.
  secret_data = join(",", [
    for email, pass in random_password.team_pass : "${email}:${pass.result}"
  ])
}

# The API reads all three at start.
resource "google_secret_manager_secret_iam_member" "api_session_secret" {
  secret_id = google_secret_manager_secret.session_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "api_guest_pass" {
  secret_id = google_secret_manager_secret.guest_pass.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "api_team_passes" {
  secret_id = google_secret_manager_secret.team_passes.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

# Named as outputs so `terraform output` says where to look, without putting the
# codes themselves into state output where CI logs could pick them up.
output "guest_pass_secret" {
  description = "gcloud secrets versions access latest --secret=<this>"
  value       = google_secret_manager_secret.guest_pass.secret_id
}

output "team_passes_secret" {
  description = "gcloud secrets versions access latest --secret=<this>"
  value       = google_secret_manager_secret.team_passes.secret_id
}
