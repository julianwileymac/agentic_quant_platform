###############################################################################
# envs/staging — same shape as dev, multi-AZ + replication enabled.
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
    session_name = "aqp-terraform-staging"
    external_id  = var.external_id
  }
  default_tags {
    tags = { managed_by = "terraform", env = "staging", repo = "agentic_quant_platform" }
  }
}

module "vpc" {
  source = "../../modules/vpc"
  name   = "aqp-staging"
  cidr   = "10.20.0.0/16"
}

module "eks" {
  source             = "../../modules/eks-cluster"
  cluster_name       = "aqp-staging"
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  kms_key_arn        = var.kms_key_arn
}

module "node_groups" {
  source       = "../../modules/eks-node-groups"
  cluster_name = module.eks.cluster_name
  subnet_ids   = module.vpc.private_subnet_ids
  desired_size = 4
  min_size     = 3
}

module "rds" {
  source      = "../../modules/rds-postgres"
  name        = "aqp-admin-staging"
  vpc_id      = module.vpc.vpc_id
  subnet_ids  = module.vpc.private_subnet_ids
  kms_key_arn = var.kms_key_arn
  multi_az    = true
}

output "cluster_name" { value = module.eks.cluster_name }
