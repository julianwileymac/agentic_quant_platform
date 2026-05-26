###############################################################################
# modules/ecr-repositories — per-service ECR with scan + lifecycle.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

variable "repositories" {
  description = "List of repo names to provision."
  type        = list(string)
  default = [
    "aqp-admin",
    "aqp-admin-frontend",
    "aqp-core",
    "aqp-ml",
    "aqp-worker",
    "aqp-ingester",
    "aqp-control-plane",
    # Bedrock AgentCore Runtime image — ARM64-only per the AWS Builders
    # walkthrough; built via aqp_platform/build/docker/aqp-agent/Dockerfile.
    "aqp-agent",
  ]
}

variable "kms_key_arn" { type = string }
variable "account_id" { type = string }
variable "region" { type = string }
variable "enable_replication" {
  type    = bool
  default = false
}
variable "replication_destination_region" {
  type    = string
  default = "us-west-2"
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_ecr_repository" "this" {
  for_each             = toset(var.repositories)
  name                 = each.value
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration { scan_on_push = true }
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = var.kms_key_arn
  }
  tags = merge(var.tags, { Name = each.value })
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each   = aws_ecr_repository.this
  repository = each.value.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 30 versioned tags"
        selection = {
          tagStatus      = "tagged"
          tagPatternList = ["v*"]
          countType      = "imageCountMoreThan"
          countNumber    = 30
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Expire untagged images > 14d old"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 14
        }
        action = { type = "expire" }
      },
    ]
  })
}

resource "aws_ecr_replication_configuration" "cross_region" {
  count = var.enable_replication ? 1 : 0
  replication_configuration {
    rule {
      destination {
        region      = var.replication_destination_region
        registry_id = var.account_id
      }
      repository_filter {
        filter      = "aqp-*"
        filter_type = "PREFIX_MATCH"
      }
    }
  }
}
