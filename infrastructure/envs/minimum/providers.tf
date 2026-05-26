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

  assume_role {
    role_arn     = "arn:aws:iam::${var.account_id}:role/AqpTerraformExecutionRole"
    session_name = "aqp-terraform-minimum"
    external_id  = var.external_id
  }

  default_tags {
    tags = {
      managed_by = "terraform"
      env        = "minimum"
      repo       = "agentic_quant_platform"
    }
  }
}
