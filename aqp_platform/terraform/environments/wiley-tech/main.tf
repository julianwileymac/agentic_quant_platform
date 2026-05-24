###############################################################################
# Wiley Tech sandbox environment — pinned to the seeded organization.
#
# Defaults to Azure since the Entra ID tenant link seeded by Alembic
# 0051 lives in Azure. Operators can override TF_VAR_cloud_provider to
# fan out into a multi-cloud experiment.
###############################################################################

terraform {
  required_version = ">= 1.10"
}

provider "azurerm" {
  features {}
}
provider "kubernetes" {
  config_path = "~/.kube/config"
}
provider "helm" {
  kubernetes {
    config_path = "~/.kube/config"
  }
}

module "aqp" {
  source            = "../../"
  cloud_provider    = "azure"
  environment       = "wiley-tech"
  organization_slug = "wiley-tech"
  workspace_slug    = "main"
  app_version       = "latest"
  azure_location    = "eastus"
}

output "namespaces" { value = module.aqp.namespaces }
output "cluster_endpoint" { value = module.aqp.cluster_endpoint }
output "registry_url" { value = module.aqp.registry_url }
output "object_store_url" { value = module.aqp.object_store_url }
output "redis_url" { value = module.aqp.redis_url }
output "ingress_host" { value = module.aqp.ingress_host }
