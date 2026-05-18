###############################################################################
# Local environment composition — k3d cluster + image build/push +
# Kubernetes workloads for the AQP stack. Replaces the docker-compose
# canonical path.
#
# Usage:
#   cd terraform/environments/local
#   terraform init
#   terraform apply
#
# Or (preferred): use the AQP CLI which routes every action through
# TerraformRuntime so each apply lands in the terraform_runs ledger
# and respects the global kill switch:
#
#   aqp deploy up
#   aqp deploy plan
#   aqp deploy build
#   aqp deploy down
###############################################################################

terraform {
  required_version = ">= 1.10"

  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.15"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}

provider "docker" {}

# Resolve the kubeconfig path lazily; the local_cluster module writes
# it during apply. Subsequent applies pick up the file from disk.
locals {
  kubeconfig_path = pathexpand("~/.kube/aqp-local.config")

  # The repo root sits three levels above this file
  # (terraform/environments/local/ -> repo root). path.cwd is the
  # directory terraform was invoked from; resolving via path.module
  # keeps the module portable when invoked from a different cwd.
  repo_root = abspath("${path.module}/../../..")
}

provider "kubernetes" {
  config_path = local.kubeconfig_path
}

provider "helm" {
  kubernetes {
    config_path = local.kubeconfig_path
  }
}

# ---------------------------------------------------------------------------
# Module wiring
#
# The k3d cluster + registry come up first (local_cluster), images
# build + push next (aqp_images), then namespaces + workloads (aqp
# root composition with cloud_provider="local").
# ---------------------------------------------------------------------------

module "local_cluster" {
  source                  = "../../modules/local_cluster"
  cloud_provider          = "local"
  environment             = var.environment
  cluster_name            = var.cluster_name
  registry_port           = var.registry_port
  lb_http_port            = var.lb_http_port
  lb_https_port           = var.lb_https_port
  kubeconfig_path         = local.kubeconfig_path
  local_shell_interpreter = var.local_shell_interpreter
  common_tags = {
    environment              = var.environment
    "managed-by"             = "terraform"
    "aqp.io/topology-target" = "local"
  }
}

module "aqp_images" {
  source                  = "../../modules/aqp_images"
  cloud_provider          = "local"
  registry_host           = module.local_cluster.registry_host
  registry_localhost      = module.local_cluster.registry_localhost
  context_path            = local.repo_root
  app_version             = var.app_version
  ready_marker            = module.local_cluster.ready
  local_shell_interpreter = var.local_shell_interpreter
}

resource "kubernetes_namespace" "aqp_local" {
  depends_on = [module.local_cluster]
  metadata {
    name = var.namespace
    labels = {
      "app.kubernetes.io/managed-by" = "terraform"
      "aqp.io/environment"           = var.environment
    }
  }
}

module "aqp_workloads" {
  source                     = "../../modules/aqp_workloads"
  cloud_provider             = "local"
  environment                = var.environment
  namespace                  = kubernetes_namespace.aqp_local.metadata[0].name
  images                     = module.aqp_images.images
  app_version                = var.app_version
  ingress_class              = "traefik"
  ready_marker               = module.aqp_images.ready
  deployment_topology_target = "local"
  enabled_services           = var.enabled_services
  common_tags = {
    environment              = var.environment
    "managed-by"             = "terraform"
    "aqp.io/topology-target" = "local"
  }

  depends_on = [
    kubernetes_namespace.aqp_local,
    module.aqp_images,
  ]
}
