variable "cloud_provider" {
  type        = string
  description = "Which cloud to provision against: local | aws | gcp | azure | rpi_cluster"
  default     = "local"

  validation {
    condition     = contains(["local", "aws", "gcp", "azure", "rpi_cluster", "docker", "baremetal", "hcp"], var.cloud_provider)
    error_message = "cloud_provider must be one of local | aws | gcp | azure | rpi_cluster | docker | baremetal | hcp"
  }
}

variable "environment" {
  type        = string
  description = "Environment slug — used in resource names + tags. local | paper | live | sandbox | wiley-tech"
  default     = "local"
}

variable "organization_slug" {
  type        = string
  description = "AQP Organization.slug owning this environment (e.g. ``wiley-tech``)"
  default     = "wiley-tech"
}

variable "workspace_slug" {
  type        = string
  description = "AQP Workspace.slug owning this environment"
  default     = "main"
}

variable "app_version" {
  type        = string
  description = "Image tag for the aqp-* container images (aqp-api, aqp-worker, aqp-agent, aqp-data-mcp, aqp-frontend, aqp-terraform-runner)."
  default     = "latest"
}

variable "namespace_prefix" {
  type        = string
  description = "Kubernetes namespace prefix (e.g. ``aqp-`` -> aqp-local, aqp-paper, aqp-live, aqp-system, aqp-backtest, aqp-terraform)."
  default     = "aqp-"
}

variable "azure_subscription_id" {
  type        = string
  default     = ""
  description = "Azure subscription id (only used when cloud_provider=azure)"
}

variable "azure_tenant_id" {
  type        = string
  default     = ""
  description = "Azure (Entra) tenant id (only used when cloud_provider=azure)"
}

variable "azure_location" {
  type    = string
  default = "eastus"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "gcp_project_id" {
  type    = string
  default = ""
}

variable "gcp_region" {
  type    = string
  default = "us-central1"
}

# ---------------------------------------------------------------------------
# Local-stack inputs.
#
# ``repo_root`` is the absolute path to the AQP repo root on the host
# running terraform apply. The aqp_images module uses it as the
# docker build context so ``docker build -t aqp-api ...`` resolves
# Dockerfile + the aqp/ tree without relying on the operator's CWD.
# Environment compositions set it to ``path.cwd/../../..`` (the repo
# root relative to terraform/environments/<env>/).
# ---------------------------------------------------------------------------

variable "repo_root" {
  type        = string
  description = "Absolute path to the AQP repository root (used as docker build context)."
  default     = ""
}

variable "auth0_enabled" {
  type        = bool
  description = "When true, provision Auth0 SPA/API/M2M/roles/actions via modules/auth0_identity."
  default     = false
}

variable "auth0_domain" {
  type        = string
  description = "Auth0 tenant domain (example: dev-abc.us.auth0.com). Auth0 provider credentials are supplied through env vars."
  default     = ""
}

variable "auth0_aqp_api_identifier" {
  type        = string
  description = "Auth0 API identifier / audience for AQP."
  default     = "https://aqp/api"
}

variable "auth0_callback_urls" {
  type        = list(string)
  description = "Allowed callback URLs for the AQP SPA."
  default     = []
}

variable "auth0_logout_urls" {
  type        = list(string)
  description = "Allowed logout URLs for the AQP SPA."
  default     = []
}

variable "auth0_web_origins" {
  type        = list(string)
  description = "Allowed web origins for the AQP SPA."
  default     = []
}

variable "auth0_sync_url" {
  type        = string
  description = "Public URL for /_internal/auth0/sync used by Auth0 post-login Action."
  default     = ""
}
