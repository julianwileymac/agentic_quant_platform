variable "region" {
  type    = string
  default = "us-east-1"
}

variable "account_id" {
  type        = string
  description = "AWS account id (must match the bootstrap state bucket account)."
}

variable "external_id" {
  type        = string
  sensitive   = true
  description = "STS external_id required by AqpTerraformExecutionRole."
}

variable "kms_key_arn" {
  type        = string
  description = "Workload CMK ARN (from infrastructure/bootstrap)."
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

# Defaults aggressively lean — flip via terraform.tfvars if you want
# multi-AZ Postgres (~2x cost) or per-AZ NAT (~$32/mo extra each).
variable "rds_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "rds_multi_az" {
  type    = bool
  default = false
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.small"
}

variable "github_deployer_repo" {
  type    = string
  default = "julianwileymac/agentic_quant_platform"
}

variable "github_oidc_provider_arn" {
  type        = string
  description = "ARN of the GitHub OIDC provider created by infrastructure/bootstrap."
}
