###############################################################################
# Root outputs — every value that downstream tooling (the AQP runner pod,
# operator scripts, the frontend control plane) needs to consume.
###############################################################################

output "namespaces" {
  description = "Kubernetes namespace map (logical name -> actual ns string)."
  value       = local.namespaces
}

output "common_tags" {
  description = "Canonical resource tag map applied across the stack."
  value       = local.common_tags
}

output "cluster_endpoint" {
  description = "Kubernetes API server endpoint (cloud-conditional)."
  value       = try(module.kubernetes.cluster_endpoint, "")
}

output "registry_url" {
  description = "Container registry hostname prefix (ECR / GAR / ACR / local)."
  value       = try(module.registry.image_base_url, "")
}

output "postgres_connection" {
  description = "Postgres connection string (Sensitive — only the host:port shown by default)."
  value       = try(module.storage.postgres_endpoint, "")
}

output "object_store_url" {
  description = "S3 / GCS / ADLS / MinIO endpoint for the AQP data lake."
  value       = try(module.storage.object_store_url, "")
}

output "redis_url" {
  description = "Redis broker / RAG vector store endpoint."
  value       = try(module.storage.redis_url, "")
}

output "ingress_host" {
  description = "Public ingress hostname (cloud-conditional)."
  value       = try(module.networking.ingress_host, "")
}

output "terraform_runner_namespace" {
  description = "Namespace hosting the aqp-terraform-runner pod."
  value       = local.namespaces["terraform"]
}
