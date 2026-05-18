output "cluster_name" {
  value = coalesce(
    try(aws_eks_cluster.aqp[0].name, null),
    try(google_container_cluster.aqp[0].name, null),
    try(azurerm_kubernetes_cluster.aqp[0].name, null),
    local.cluster_name,
  )
}

# NOTE: ``cluster_endpoint`` and ``namespaces`` live in main.tf as the
# canonical outputs. The earlier duplicates here are removed to silence
# the "Duplicate output definition" terraform-init errors. ``cluster_name``
# above stays here because it's only declared in this file.
