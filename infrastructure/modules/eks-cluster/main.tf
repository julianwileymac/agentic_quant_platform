###############################################################################
# modules/eks-cluster — EKS 1.32 control plane + IRSA + addons.
#
# Wraps the official `terraform-aws-modules/eks/aws` module with AQP's
# defaults: private endpoint only, all 5 control-plane logs, OIDC
# provider auto-created, EKS Auto Mode disabled (so we control the
# Karpenter NodePools per blueprint §6.2).
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws        = { source = "hashicorp/aws",        version = "~> 5.70" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.32" }
    helm       = { source = "hashicorp/helm",       version = "~> 2.16" }
  }
}

variable "cluster_name" { type = string }
variable "cluster_version" {
  type    = string
  default = "1.32"
}
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "kms_key_arn" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.30"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  cluster_endpoint_public_access  = false
  cluster_endpoint_private_access = true

  cluster_enabled_log_types = [
    "api",
    "audit",
    "authenticator",
    "controllerManager",
    "scheduler",
  ]

  vpc_id     = var.vpc_id
  subnet_ids = var.private_subnet_ids

  enable_cluster_creator_admin_permissions = false
  authentication_mode                      = "API"

  cluster_encryption_config = {
    resources        = ["secrets"]
    provider_key_arn = var.kms_key_arn
  }

  cluster_addons = {
    vpc-cni = {
      most_recent = true
      configuration_values = jsonencode({
        env = { ENABLE_PREFIX_DELEGATION = "true" }
      })
    }
    coredns                = { most_recent = true }
    kube-proxy             = { most_recent = true }
    eks-pod-identity-agent = { most_recent = true }
    aws-ebs-csi-driver     = { most_recent = true }
    aws-efs-csi-driver     = { most_recent = true }
  }

  tags = merge(var.tags, { Name = var.cluster_name })
}
