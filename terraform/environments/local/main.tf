###############################################################################
# Local environment composition — minikube/kind + Docker for storage.
#
# `terraform -chdir=terraform/environments/local init` from the repo root
# bootstraps a fully self-contained local stack.
###############################################################################

terraform {
  required_version = ">= 1.10"
}

provider "docker" {}
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
  cloud_provider     = "local"
  environment        = "local"
  organization_slug  = "wiley-tech"
  workspace_slug     = "main"
  app_version        = "latest"
}

output "namespaces"   { value = module.aqp.namespaces }
output "redis_url"    { value = module.aqp.redis_url }
output "ingress_host" { value = module.aqp.ingress_host }
