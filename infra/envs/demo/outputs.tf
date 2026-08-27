output "ingress_ip" {
  description = "Point the A record for the domain here."
  value       = google_compute_global_address.ingress.address
}

output "dns_record" {
  description = "Paste this into the DNS provider."
  value = {
    type  = "A"
    host  = split(".", var.domain)[0]
    value = google_compute_global_address.ingress.address
    ttl   = 3600
  }
}

output "clickhouse_endpoints" {
  description = "Endpoints for migrations and the MCP server."
  value       = clickhouse_service.main.endpoints
}

output "buckets" {
  value = {
    originals = google_storage_bucket.originals.name
    proxies   = google_storage_bucket.proxies.name
    artifacts = google_storage_bucket.artifacts.name
  }
}

output "ingest_topic" {
  value = google_pubsub_topic.ingest.name
}

output "artifact_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}
