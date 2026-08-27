/**
 * These become GitHub repository secrets. None of them is a credential — the
 * provider name and service account email are useless to anyone whose workflow
 * does not run in the bound repository.
 */

output "tf_state_bucket" {
  description = "Set as TF_STATE_BUCKET. The backend for every environment."
  value       = google_storage_bucket.tfstate.name
}

output "workload_identity_provider" {
  description = "Set as GCP_WORKLOAD_IDENTITY_PROVIDER."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "deployer_service_account" {
  description = "Set as GCP_SERVICE_ACCOUNT."
  value       = google_service_account.deployer.email
}

output "next_steps" {
  description = "What to do with the values above."
  value       = <<-EOT

    Bootstrap complete. Add these to GitHub → Settings → Secrets → Actions:

      TF_STATE_BUCKET                 ${google_storage_bucket.tfstate.name}
      GCP_WORKLOAD_IDENTITY_PROVIDER  ${google_iam_workload_identity_pool_provider.github.name}
      GCP_SERVICE_ACCOUNT             ${google_service_account.deployer.email}
      GCP_PROJECT_ID                  ${var.project_id}
      GCP_REGION                      ${var.region}

    Then add the ClickHouse Cloud credentials from the ClickHouse console:

      CLICKHOUSE_ORG_ID
      CLICKHOUSE_TOKEN_KEY
      CLICKHOUSE_TOKEN_SECRET

    After that, every deployment happens on push to main.
  EOT
}
