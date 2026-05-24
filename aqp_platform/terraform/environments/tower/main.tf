terraform {
  required_version = ">= 1.10"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.6"
    }
  }
}

provider "kubernetes" {
  config_path    = pathexpand(var.kubeconfig_path)
  config_context = var.kube_context != "" ? var.kube_context : null
}

provider "cloudflare" {
  # API token is resolved from CLOUDFLARE_API_TOKEN.
}

locals {
  common_tags = {
    environment              = "tower"
    "managed-by"             = "terraform"
    target                   = "aqp-two-node"
    "aqp.io/topology-target" = "tower"
  }

  images = {
    api      = "${var.image_registry}/aqp-api:${var.app_version}"
    worker   = "${var.image_registry}/aqp-worker:${var.app_version}"
    beat     = "${var.image_registry}/aqp-beat:${var.app_version}"
    frontend = "${var.image_registry}/aqp-frontend:${var.app_version}"
    cp       = "${var.image_registry}/aqp-control-plane:${var.app_version}"
  }
}

module "target" {
  source                 = "../../modules/rpi_kubernetes_target"
  namespace              = var.namespace
  common_tags            = local.common_tags
  auth0_domain           = var.auth0_domain
  auth0_audience         = var.auth0_audience
  auth0_client_id        = var.auth0_client_id
  auth_scim_m2m_audience = var.auth_scim_m2m_audience
  ingress_host           = var.ingress_host
}

module "aqp_workloads" {
  source                                  = "../../modules/aqp_workloads"
  cloud_provider                          = "rpi_cluster"
  environment                             = "tower"
  namespace                               = module.target.namespace
  namespaces                              = { admin = module.target.admin_namespace }
  images                                  = local.images
  app_version                             = var.app_version
  ingress_class                           = "nginx"
  common_tags                             = local.common_tags
  ready_marker                            = var.app_version
  deployment_topology_target              = "tower"
  enabled_services                        = var.enabled_services
  auth_config_map_name                    = module.target.auth_config_map
  frontend_auth_config_map_name           = module.target.frontend_auth_config_map
  control_plane_auth_config_map_name      = module.target.admin_auth_config_map
  auth0_client_secret_secret_name         = var.auth0_client_secret_secret_name
  auth_scim_bearer_token_hash_secret_name = var.auth_scim_bearer_token_hash_secret_name

  depends_on = [module.target]
}

module "cloudflare_edge" {
  count  = var.cloudflare_enabled ? 1 : 0
  source = "../../modules/cloudflare_edge"

  tunnel_name                 = var.cloudflare_tunnel_name
  account_id                  = var.cloudflare_account_id
  zone_id                     = var.cloudflare_zone_id
  ingress_rules               = var.cloudflare_ingress_rules
  enable_access_app           = var.cloudflare_enable_access_app
  access_app_name             = var.cloudflare_access_app_name
  access_app_session_duration = var.cloudflare_access_app_session_duration
  access_policies             = var.cloudflare_access_policies
}
