###############################################################################
# Paper trading environment — GCP GKE by default (operator-overridable).
###############################################################################

terraform {
  required_version = ">= 1.10"
}

provider "google" {
  project = "wiley-tech-paper"
  region  = "us-central1"
}
provider "kubernetes" {
  # In CI the runner pod loads the GKE kubeconfig from the matching
  # cloud KubernetesAdapter; here we point at a kubeconfig file the
  # operator can update.
  config_path = "~/.kube/config"
}
provider "helm" {
  kubernetes {
    config_path = "~/.kube/config"
  }
}

module "aqp" {
  source            = "../../"
  cloud_provider    = "gcp"
  environment       = "paper"
  organization_slug = "wiley-tech"
  workspace_slug    = "main"
  app_version       = "latest"
}

output "namespaces" { value = module.aqp.namespaces }
output "cluster_endpoint" { value = module.aqp.cluster_endpoint }
output "registry_url" { value = module.aqp.registry_url }
output "redis_url" { value = module.aqp.redis_url }
output "ingress_host" { value = module.aqp.ingress_host }
