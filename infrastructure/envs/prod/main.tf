###############################################################################
# envs/prod — production composition.
#
# Multi-AZ everything, multi-region ECR + S3 CRR, larger compute pools,
# stricter NodePool requirements (on-demand only for the compute pool).
###############################################################################

variable "region" { type = string; default = "us-east-1" }
variable "account_id" { type = string }
variable "external_id" {
  type      = string
  sensitive = true
}
variable "kms_key_arn" { type = string }
variable "github_oidc_provider_arn" { type = string }
variable "grafana_admin_password" {
  type      = string
  sensitive = true
}

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws        = { source = "hashicorp/aws",        version = "~> 5.70" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.32" }
    helm       = { source = "hashicorp/helm",       version = "~> 2.16" }
    random     = { source = "hashicorp/random",     version = "~> 3.6" }
  }
  backend "s3" {}
}

provider "aws" {
  region = var.region
  assume_role {
    role_arn     = "arn:aws:iam::${var.account_id}:role/AqpTerraformExecutionRole"
    session_name = "aqp-terraform-prod"
    external_id  = var.external_id
  }
  default_tags {
    tags = { managed_by = "terraform", env = "prod", repo = "agentic_quant_platform" }
  }
}

module "vpc" {
  source    = "../../modules/vpc"
  name      = "aqp-prod"
  cidr      = "10.30.0.0/16"
  azs_count = 3
}

module "eks" {
  source             = "../../modules/eks-cluster"
  cluster_name       = "aqp-prod"
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  kms_key_arn        = var.kms_key_arn
}

module "node_groups" {
  source         = "../../modules/eks-node-groups"
  cluster_name   = module.eks.cluster_name
  subnet_ids     = module.vpc.private_subnet_ids
  instance_types = ["m6i.xlarge", "m6i.2xlarge"]
  min_size       = 3
  max_size       = 30
  desired_size   = 6
}

module "rds" {
  source      = "../../modules/rds-postgres"
  name        = "aqp-admin-prod"
  vpc_id      = module.vpc.vpc_id
  subnet_ids  = module.vpc.private_subnet_ids
  kms_key_arn = var.kms_key_arn
  multi_az    = true
}

output "cluster_name" { value = module.eks.cluster_name }
