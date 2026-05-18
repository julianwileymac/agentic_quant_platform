###############################################################################
# AQP Terraform — root composition.
#
# Environment-specific TF_VAR_cloud_provider + TF_VAR_environment select
# which module set actually runs. Each module is conditional via the
# ``count`` meta-argument or a per-cloud locals block so the unused
# providers stay dormant at plan time.
#
# To init/plan a specific environment, prefer the matching
# ``terraform/environments/<env>/`` composition over this root — those
# files set TF_VAR defaults and pin the right state backend.
###############################################################################

locals {
  common_tags = {
    environment      = var.environment
    "managed-by"     = "terraform"
    organization     = var.organization_slug
    workspace        = var.workspace_slug
    version          = var.app_version
  }

  # Canonical AQP namespace map. Every cloud + local target carves out
  # the same namespaces so cross-environment manifests are portable.
  namespaces = {
    local     = "${var.namespace_prefix}local"
    paper     = "${var.namespace_prefix}paper"
    live      = "${var.namespace_prefix}live"
    backtest  = "${var.namespace_prefix}backtest"
    system    = "${var.namespace_prefix}system"
    terraform = "${var.namespace_prefix}terraform"
    bots      = "${var.namespace_prefix}bots"
    agents    = "${var.namespace_prefix}agents"
  }
}

module "networking" {
  source             = "./modules/networking"
  cloud_provider     = var.cloud_provider
  environment        = var.environment
  organization_slug  = var.organization_slug
  workspace_slug     = var.workspace_slug
  common_tags        = local.common_tags
}

module "kubernetes" {
  source             = "./modules/kubernetes"
  cloud_provider     = var.cloud_provider
  environment        = var.environment
  organization_slug  = var.organization_slug
  workspace_slug     = var.workspace_slug
  common_tags        = local.common_tags
  namespaces         = local.namespaces
  networking_outputs = module.networking
}

module "registry" {
  source             = "./modules/registry"
  cloud_provider     = var.cloud_provider
  environment        = var.environment
  common_tags        = local.common_tags
}

module "secrets" {
  source              = "./modules/secrets"
  cloud_provider      = var.cloud_provider
  environment         = var.environment
  common_tags         = local.common_tags
  namespaces          = local.namespaces
  kubernetes_outputs  = module.kubernetes
}

module "storage" {
  source              = "./modules/storage"
  cloud_provider      = var.cloud_provider
  environment         = var.environment
  organization_slug   = var.organization_slug
  common_tags         = local.common_tags
  networking_outputs  = module.networking
  kubernetes_outputs  = module.kubernetes
}

module "database" {
  source              = "./modules/database"
  cloud_provider      = var.cloud_provider
  environment         = var.environment
  common_tags         = local.common_tags
  storage_outputs     = module.storage
  kubernetes_outputs  = module.kubernetes
  app_version         = var.app_version
}

module "pipeline" {
  source              = "./modules/pipeline"
  cloud_provider      = var.cloud_provider
  environment         = var.environment
  common_tags         = local.common_tags
  storage_outputs     = module.storage
  kubernetes_outputs  = module.kubernetes
  app_version         = var.app_version
}

module "faas" {
  source              = "./modules/faas"
  cloud_provider      = var.cloud_provider
  environment         = var.environment
  common_tags         = local.common_tags
  namespaces          = local.namespaces
  storage_outputs     = module.storage
  app_version         = var.app_version
}

module "agents" {
  source              = "./modules/agents"
  cloud_provider      = var.cloud_provider
  environment         = var.environment
  common_tags         = local.common_tags
  namespaces          = local.namespaces
  storage_outputs     = module.storage
  app_version         = var.app_version
}
