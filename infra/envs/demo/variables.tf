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
