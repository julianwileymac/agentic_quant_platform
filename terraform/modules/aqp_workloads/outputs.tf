###############################################################################
# aqp_workloads — outputs.
###############################################################################

output "enabled" {
  description = "True when the active cloud_provider engages this module."
  value       = local.is_local
}

output "namespace" {
  description = "Kubernetes namespace AQP services landed in."
  value       = var.namespace
}

output "api_service" {
  description = "ClusterIP service name for the API."
  value       = local.is_local && local.api_image != "" ? kubernetes_service.aqp_api[0].metadata[0].name : ""
}

output "frontend_service" {
  description = "ClusterIP service name for the frontend bundle."
  value       = local.is_local && local.frontend_image != "" ? kubernetes_service.aqp_frontend[0].metadata[0].name : ""
}

output "ingress_name" {
  description = "Ingress object name for AQP routes."
  value       = local.is_local && local.api_image != "" ? kubernetes_ingress_v1.aqp[0].metadata[0].name : ""
}

output "ready" {
  description = "Pseudo-output downstream consumers depend on once every workload has been scheduled."
  value = local.is_local ? join(",", concat(
    [for d in kubernetes_deployment.aqp_api : d.id],
    [for d in kubernetes_deployment.aqp_worker : d.id],
    [for d in kubernetes_deployment.aqp_beat : d.id],
    [for d in kubernetes_deployment.aqp_frontend : d.id],
  )) : ""
}
