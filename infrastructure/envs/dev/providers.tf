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
    session_name = "aqp-terraform-dev"
    external_id  = var.external_id
  }

  default_tags {
    tags = {
      managed_by = "terraform"
      env        = "dev"
      repo       = "agentic_quant_platform"
    }
  }
}

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args = ["eks", "get-token", "--cluster-name", module.eks.cluster_name, "--region", var.region]
  }
}

provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args = ["eks", "get-token", "--cluster-name", module.eks.cluster_name, "--region", var.region]
    }
  }
}
