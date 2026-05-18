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
  type        = string
  default     = "eastus"
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
