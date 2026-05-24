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

# ---------------------------------------------------------------------------
# Local stack endpoints. Empty strings on cloud installs.
# ---------------------------------------------------------------------------

output "local_stack_enabled" {
  description = "True when the active cloud_provider engages the local k3d stack."
  value       = module.local_cluster.enabled
}

output "local_cluster_name" {
  description = "k3d cluster name."
  value       = module.local_cluster.cluster_name
}

output "local_kubeconfig_path" {
  description = "Filesystem path to the kubeconfig the kubernetes/helm providers should read."
  value       = module.local_cluster.kubeconfig_path
}

output "local_registry_host" {
  description = "Image registry host:port the cluster pulls from."
  value       = module.local_cluster.registry_host
}

output "local_registry_localhost" {
  description = "Image registry host:port reachable from the host shell."
  value       = module.local_cluster.registry_localhost
}

output "local_namespace" {
  description = "Kubernetes namespace AQP services land in for the local target."
  value       = local.namespaces["local"]
}

output "local_endpoints" {
  description = "Map of human-friendly URL endpoints for the local stack (empty on cloud installs)."
  value = module.local_cluster.enabled ? {
    api      = "http://localhost:${module.local_cluster.lb_http_port}/api"
    frontend = "http://localhost:${module.local_cluster.lb_http_port}/"
    mlflow   = "http://mlflow.${local.namespaces["local"]}.svc.cluster.local:5000"
    jaeger   = "http://jaeger.${local.namespaces["local"]}.svc.cluster.local:16686"
  } : {}
}
