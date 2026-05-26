###############################################################################
# bootstrap/ — one-time seed.
#
# Hand-applied with LOCAL state (no backend block) before any other
# composition. Provisions:
#
#   - The S3 bucket that holds remote state for every other stack
#   - The KMS customer-managed key that encrypts state + secrets
#   - A DynamoDB table reserved as the legacy lock backend (unused
#     when the AWS provider's native S3 locking is on)
#   - The GitHub Actions OIDC provider trust (one per account)
#
# After this stack applies once, every other composition references
# its outputs via `data` blocks; never re-applied except to update
# the OIDC thumbprints.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

variable "account_alias" {
  description = "Short alias for this account (e.g. 'shared', 'dev', 'staging', 'prod')."
  type        = string
}

variable "region" {
  description = "Primary AWS region."
  type        = string
  default     = "us-east-1"
}

variable "github_org" {
  description = "GitHub organization that owns the source repo."
  type        = string
  default     = "julianwileymac"
}

variable "github_repo" {
  description = "GitHub repository name for the OIDC trust subject filter."
  type        = string
  default     = "agentic_quant_platform"
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      managed_by = "terraform"
      stack      = "bootstrap"
      repo       = "agentic_quant_platform"
      account    = var.account_alias
    }
  }
}

###############################################################################
# KMS customer-managed key for state + every per-account secret bucket.
###############################################################################

resource "aws_kms_key" "tfstate" {
  description             = "AQP Terraform state + audit-archive encryption (${var.account_alias})"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  key_usage               = "ENCRYPT_DECRYPT"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "RootAccountAdmin"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "TerraformExecutionRoleDecrypt"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/AqpTerraformExecutionRole" }
        Action = [
          "kms:Decrypt",
          "kms:Encrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/team" = "platform"
          }
        }
      }
    ]
  })
}

resource "aws_kms_alias" "tfstate" {
  name          = "alias/aqp-tfstate"
  target_key_id = aws_kms_key.tfstate.key_id
}

data "aws_caller_identity" "current" {}

###############################################################################
# Remote state bucket — versioned, KMS-encrypted, Object-Lock-protected.
###############################################################################

resource "aws_s3_bucket" "tfstate" {
  bucket        = "aqp-tfstate-${var.account_alias}"
  force_destroy = false

  object_lock_enabled = true
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.tfstate.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_object_lock_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    default_retention {
      mode = "GOVERNANCE"
      days = 30
    }
  }
}

resource "aws_s3_bucket_policy" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyAllExceptTerraformExecutionRole"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.tfstate.arn,
          "${aws_s3_bucket.tfstate.arn}/*",
        ]
        Condition = {
          StringNotEquals = {
            "aws:PrincipalArn" = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/AqpTerraformExecutionRole"
          }
          Bool = { "aws:SecureTransport" = "true" }
        }
      }
    ]
  })
}

###############################################################################
# DynamoDB legacy lock table — reserved for one-line rollback if the
# native S3 locking ever needs to be turned off.
###############################################################################

resource "aws_dynamodb_table" "tfstate_lock_legacy" {
  name         = "aqp-tfstate-lock-${var.account_alias}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.tfstate.arn
  }

  tags = {
    purpose = "legacy-lock-rollback"
  }
}

###############################################################################
# GitHub Actions OIDC provider — trust between this account and the
# `julianwileymac/agentic_quant_platform` repository.
###############################################################################

data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = data.tls_certificate.github.certificates[*].sha1_fingerprint
}
