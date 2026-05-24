###############################################################################
# local_cluster — outputs.
###############################################################################

output "enabled" {
  description = "True when the active cloud_provider engages this module."
  value       = local.is_local
}

output "cluster_name" {
  description = "k3d cluster name (matches the input variable)."
  value       = var.cluster_name
}

output "registry_host" {
  description = "Image registry host:port reachable from the host AND the cluster."
  value       = "${var.registry_name}:${var.registry_port}"
}

output "registry_localhost" {
  description = "Registry host:port reachable from outside the cluster (used for docker push)."
  value       = "localhost:${var.registry_port}"
}

output "kubeconfig_path" {
  description = "Filesystem path to the merged kubeconfig the kubernetes / helm providers should read."
  value       = var.kubeconfig_path
}

output "lb_http_port" {
  description = "Host port mapped to Traefik :80."
  value       = var.lb_http_port
}

output "lb_https_port" {
  description = "Host port mapped to Traefik :443."
  value       = var.lb_https_port
}

# Cluster-internal mark used by downstream modules to depend_on the
# cluster's readiness without re-running the create provisioner.
output "ready" {
  description = "Pseudo-output downstream modules can depend on for ordering."
  value       = local.is_local ? null_resource.wait_for_api[0].id : ""
}
