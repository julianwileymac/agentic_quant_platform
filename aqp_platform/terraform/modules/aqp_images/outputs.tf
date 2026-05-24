###############################################################################
# aqp_images — outputs.
###############################################################################

output "enabled" {
  description = "True when the active cloud_provider engages this module."
  value       = local.is_local
}

output "images" {
  description = "Logical service name -> registry-qualified image reference (cluster-side host)."
  value = local.is_local ? merge(
    {
      for name, _ in local.images :
      name => "${var.registry_host}/aqp-${name}:${var.app_version}"
    },
    {
      frontend = "${var.registry_host}/aqp-frontend:${var.app_version}"
    },
  ) : {}
}

output "ready" {
  description = "Pseudo-output downstream modules depend on so workloads only deploy after every image push completed."
  value = local.is_local ? join(",", concat(
    [for r in null_resource.backend_image : r.id],
    [for r in null_resource.frontend_image : r.id],
  )) : ""
}
