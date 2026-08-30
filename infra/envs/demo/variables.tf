variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "clickhouse_org_id" {
  type      = string
  sensitive = true
}

variable "clickhouse_token_key" {
  type      = string
  sensitive = true
}

variable "clickhouse_token_secret" {
  type      = string
  sensitive = true
}

variable "clickhouse_region" {
  description = "Keep this close to the GCP region. Cross-region round trips on every query add up faster than the storage does."
  type        = string
  default     = "us-central1"
}

variable "allowed_origins" {
  description = "Origins permitted to upload directly to storage. Browsers enforce this, so it is a real boundary, not decoration."
  type        = list(string)
  default = [
    "https://trimbin.qlitch.com",
    "http://localhost:3000",
  ]
}

variable "domain" {
  type    = string
  default = "trimbin.qlitch.com"
}

variable "oauth_client_id" {
  description = <<-EOT
    The Web OAuth 2.0 client ID that Google sign-in tokens are minted for.

    The one thing here Terraform does not create, and not for want of trying.
    Google exposes OAuth client creation through the API only for organisation
    -internal consent screens (google_iap_brand with INTERNAL). This project has
    no organisation — it sits under a personal account — so the consent screen
    must be external, and external clients are console-only. There is no
    provider resource, no gcloud command, and no REST endpoint for it.

    So the value is created once by hand and everything after it is Terraform's:
    it arrives as a GitHub secret, becomes an environment variable on Cloud Run
    here, and the API refuses every bearer token while it is empty rather than
    accepting tokens minted for somebody else's application.

    See docs/oauth-client.md for exactly what to click.
  EOT
  type        = string
  default     = ""
  sensitive   = false # a client ID is public by design; the secret is the secret
}

# The guest password, shown on the sign-in form.
#
# Deliberately readable and deliberately in git: it is displayed to every
# visitor, so hiding it would be theatre. The editors' passwords are generated
# and never leave Secret Manager.
variable "guest_password" {
  description = "Shown on the sign-in form. Not a secret."
  type        = string
  default     = "guest12345"
}

# The company, as Terraform needs to know it: one pass is generated per address.
#
# Duplicated from services/members.py, which is the source of truth for what
# each of them may do. Two lists is a real cost and the alternative is worse —
# Terraform cannot import Python, and a pass generated for somebody the roster
# does not know would sign them in as a guest, silently, which is the confusing
# kind of wrong.
variable "editor_emails" {
  description = "Addresses that get a team pass. Must match services/members.py."
  type        = list(string)
  default = [
    "tanvir4hmed@gmail.com",
    "dipon778@gmail.com",
    "mohidewan10@gmail.com",
  ]
}
