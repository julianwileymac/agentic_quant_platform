###############################################################################
# Live trading environment — AWS Multi-AZ with prod sizing.
###############################################################################

terraform {
  required_version = ">= 1.10"
}

provider "aws" {
  region = "us-east-1"
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
  source             = "../../"
  cloud_provider     = "aws"
  environment        = "live"
  organization_slug  = "wiley-tech"
  workspace_slug     = "main"
  app_version        = "latest"
  aws_region         = "us-east-1"
}

output "namespaces"       { value = module.aqp.namespaces }
output "cluster_endpoint" { value = module.aqp.cluster_endpoint }
output "registry_url"     { value = module.aqp.registry_url }
output "object_store_url" { value = module.aqp.object_store_url }
output "redis_url"        { value = module.aqp.redis_url }
output "ingress_host"     { value = module.aqp.ingress_host }
