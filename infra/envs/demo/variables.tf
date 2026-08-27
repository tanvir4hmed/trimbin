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
