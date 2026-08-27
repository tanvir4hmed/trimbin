variable "project_id" {
  description = "Google Cloud project id. Created by hand — Terraform cannot authenticate to a project that does not exist yet."
  type        = string
}

variable "region" {
  description = "Primary region. Keep media, compute and ClickHouse close to each other; cross-region egress on video is expensive."
  type        = string
  default     = "us-central1"
}

variable "github_repository" {
  description = "owner/repo. Binds the federated identity to exactly one repository — without it, any repository could assume the deployer."
  type        = string

  validation {
    condition     = can(regex("^[^/]+/[^/]+$", var.github_repository))
    error_message = "Must be in owner/repo form, e.g. tanvir4hmed/trimbin."
  }
}

variable "billing_account_id" {
  description = "Billing account for the budget guard. Leave empty to skip — the guard needs billing-level permission that not every account has."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Alert thresholds fire at 50%, 80% and 100% of this."
  type        = number
  default     = 100
}
