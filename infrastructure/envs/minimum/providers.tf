###############################################################################
# envs/minimum — single-account, lowest-cost AQP footprint.
#
# Mirrors envs/dev/providers.tf but drops the K8s / Helm providers (no EKS).
# The state backend is partial S3; render backend.hcl from the
# infrastructure/bootstrap/ outputs before ``terraform init``.
###############################################################################
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws    = { source = "hashicorp/aws",    version = "~> 5.70" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
  backend "s3" {}
}

provider "aws" {
  region = var.region

  # Single-account minimum tier — uses the caller's default session
  # directly (no assume-role hop). For multi-account topologies, the
  # full envs/dev|staging|prod composition uses the
  # ``AqpTerraformExecutionRole`` indirection instead.
  # When ``AQP_TF_ASSUME_ROLE_ARN`` is set, assume that role; otherwise
  # the default credential chain is used as-is.
  dynamic "assume_role" {
    for_each = var.assume_role_arn != "" ? [1] : []
    content {
      role_arn     = var.assume_role_arn
      session_name = "aqp-terraform-minimum"
      external_id  = var.external_id != "" ? var.external_id : null
    }
  }

  default_tags {
    tags = {
      managed_by = "terraform"
      env        = "minimum"
      repo       = "agentic_quant_platform"
    }
  }
}
