output "namespace" {
  value = kubernetes_namespace.aqp.metadata[0].name
}

output "admin_namespace" {
  value = kubernetes_namespace.aqp_admin.metadata[0].name
}

output "auth_config_map" {
  value = kubernetes_config_map.cluster_auth.metadata[0].name
}

output "frontend_auth_config_map" {
  value = kubernetes_config_map.frontend_auth.metadata[0].name
}

output "admin_auth_config_map" {
  value = kubernetes_config_map.admin_auth.metadata[0].name
}
