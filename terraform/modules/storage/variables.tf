variable "cloud_provider" {
  description = "Target cloud provider: local | aws | gcp | azure"
  type        = string
  validation {
    condition     = contains(["local", "aws", "gcp", "azure"], var.cloud_provider)
    error_message = "cloud_provider must be one of local | aws | gcp | azure"
  }
}

variable "environment" {
  description = "Environment label (local | paper | live | sandbox | wiley-tech)"
  type        = string
}

variable "organization_slug" {
  description = "Owning AQP Organization slug; stamped on every resource tag."
  type        = string
  default     = "wiley-tech"
}

variable "namespace_prefix" {
  description = "k8s namespace prefix for in-cluster resources"
  type        = string
  default     = "aqp"
}

variable "postgres_engine_version" {
  type    = string
  default = "16"
}

variable "postgres_storage_gb" {
  type    = number
  default = 100
}

variable "postgres_multi_az" {
  type    = bool
  default = true
}

variable "postgres_connection_limit" {
  type    = number
  default = 200
}

variable "bucket_name" {
  description = "Object-store bucket name (must be globally unique on cloud targets)"
  type        = string
  default     = ""
}

variable "redis_memory_gb" {
  type    = number
  default = 1
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_subnet_ids" {
  type    = list(string)
  default = []
}

variable "gcp_project_id" {
  type    = string
  default = ""
}

variable "gcp_region" {
  type    = string
  default = "us-central1"
}

variable "azure_subscription_id" {
  type    = string
  default = ""
}

variable "azure_tenant_id" {
  type    = string
  default = ""
}

variable "azure_resource_group" {
  type    = string
  default = ""
}

variable "azure_location" {
  type    = string
  default = "eastus"
}

variable "common_tags" {
  type    = map(string)
  default = {}
}
