###############################################################################
# Local environment outputs.
#
# The aqp deploy CLI pulls these via ``terraform output -json`` to
# print human-friendly endpoints + populate the frontend Local Stack
# panel after every apply. Add a new output when wiring a new service.
###############################################################################

output "cluster_name" {
  description = "k3d cluster name."
  value       = module.local_cluster.cluster_name
}

output "kubeconfig_path" {
  description = "Filesystem path to the merged kubeconfig the kubernetes / helm providers read."
  value       = module.local_cluster.kubeconfig_path
}

output "registry_host" {
  description = "Image registry host:port the cluster pulls from."
  value       = module.local_cluster.registry_host
}

output "registry_localhost" {
  description = "Image registry host:port reachable from the host shell."
  value       = module.local_cluster.registry_localhost
}

output "namespace" {
  description = "Kubernetes namespace AQP services land in."
  value       = kubernetes_namespace.aqp_local.metadata[0].name
}

output "api_url" {
  description = "AQP API base URL reachable from the host."
  value       = "http://localhost:${module.local_cluster.lb_http_port}/api"
}

output "frontend_url" {
  description = "AQP Vite frontend URL reachable from the host."
  value       = "http://localhost:${module.local_cluster.lb_http_port}/"
}

output "mlflow_url_in_cluster" {
  description = "MLflow tracking endpoint (cluster-internal)."
  value       = "http://mlflow.${kubernetes_namespace.aqp_local.metadata[0].name}.svc.cluster.local:5000"
}

output "jaeger_url_in_cluster" {
  description = "Jaeger UI endpoint (cluster-internal). Port-forward to access from the host."
  value       = "http://jaeger.${kubernetes_namespace.aqp_local.metadata[0].name}.svc.cluster.local:16686"
}

output "endpoints" {
  description = "Map of every operator-facing endpoint. The frontend Local Stack card consumes this verbatim."
  value = {
    api        = "http://localhost:${module.local_cluster.lb_http_port}/api"
    frontend   = "http://localhost:${module.local_cluster.lb_http_port}/"
    mlflow     = "http://mlflow.${kubernetes_namespace.aqp_local.metadata[0].name}.svc.cluster.local:5000"
    jaeger     = "http://jaeger.${kubernetes_namespace.aqp_local.metadata[0].name}.svc.cluster.local:16686"
    cluster    = module.local_cluster.cluster_name
    namespace  = kubernetes_namespace.aqp_local.metadata[0].name
    registry   = module.local_cluster.registry_localhost
    kubeconfig = module.local_cluster.kubeconfig_path
  }
}
