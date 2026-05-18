output "cluster_name" {
  value = coalesce(
    try(aws_eks_cluster.aqp[0].name, null),
    try(google_container_cluster.aqp[0].name, null),
    try(azurerm_kubernetes_cluster.aqp[0].name, null),
    local.cluster_name,
  )
}

output "cluster_endpoint" {
  value = coalesce(
    try(aws_eks_cluster.aqp[0].endpoint, null),
    try("https://${google_container_cluster.aqp[0].endpoint}", null),
    try(azurerm_kubernetes_cluster.aqp[0].fqdn, null),
    "https://localhost:8443",
  )
  sensitive = true
}

output "namespaces" {
  value = [for ns in kubernetes_namespace.aqp : ns.metadata[0].name]
}
