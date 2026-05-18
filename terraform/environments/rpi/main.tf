terraform {
  required_version = ">= 1.10"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
  }
}

provider "kubernetes" {
  config_path    = pathexpand(var.rpi_kubeconfig_path)
  config_context = var.rpi_kube_context != "" ? var.rpi_kube_context : null
}

locals {
  common_tags = {
    environment              = "rpi"
    "managed-by"             = "terraform"
    target                   = "rpi_kubernetes"
    "aqp.io/topology-target" = "rpi"
  }

  images = {
    api      = "${var.rpi_image_registry}/aqp-api:${var.app_version}"
    worker   = "${var.rpi_image_registry}/aqp-worker:${var.app_version}"
    beat     = "${var.rpi_image_registry}/aqp-beat:${var.app_version}"
    frontend = "${var.rpi_image_registry}/aqp-frontend:${var.app_version}"
  }
}

module "target" {
  source                 = "../../modules/rpi_kubernetes_target"
  namespace              = var.rpi_namespace
  common_tags            = local.common_tags
  auth0_domain           = var.auth0_domain
  auth0_audience         = var.auth0_audience
  auth0_client_id        = var.auth0_client_id
  auth_scim_m2m_audience = var.auth_scim_m2m_audience
  ingress_host           = var.rpi_ingress_host
}

module "aqp_workloads" {
  source                                  = "../../modules/aqp_workloads"
  cloud_provider                          = "rpi_cluster"
  environment                             = "rpi"
  namespace                               = module.target.namespace
  images                                  = local.images
  app_version                             = var.app_version
  ingress_class                           = "nginx"
  common_tags                             = local.common_tags
  ready_marker                            = var.app_version
  deployment_topology_target              = "rpi"
  enabled_services                        = var.enabled_services
  auth_config_map_name                    = module.target.auth_config_map
  frontend_auth_config_map_name           = module.target.frontend_auth_config_map
  auth0_client_secret_secret_name         = var.auth0_client_secret_secret_name
  auth_scim_bearer_token_hash_secret_name = var.auth_scim_bearer_token_hash_secret_name

  depends_on = [module.target]
}
