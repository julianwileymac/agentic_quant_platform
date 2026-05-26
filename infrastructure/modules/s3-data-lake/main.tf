###############################################################################
# modules/s3-data-lake — Parquet bucket + Object-Lock variant for audit.
#
# `enable_object_lock = true` flips the bucket into the Compliance-mode
# WORM tier with a 7-year retention policy per FINRA Rule 4511 + SEC
# Rule 17a-4(f)(2)(i)(B). Used for the audit-archive bucket only.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

variable "name" { type = string }
variable "kms_key_arn" { type = string }
variable "enable_object_lock" {
  type    = bool
  default = false
}
variable "object_lock_retention_years" {
  type    = number
  default = 7
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_s3_bucket" "this" {
  bucket              = var.name
  force_destroy       = false
  object_lock_enabled = var.enable_object_lock
  tags                = var.tags
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_object_lock_configuration" "this" {
  count  = var.enable_object_lock ? 1 : 0
  bucket = aws_s3_bucket.this.id
  rule {
    default_retention {
      mode  = "COMPLIANCE"
      years = var.object_lock_retention_years
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    id     = "audit-archive-tiering"
    status = "Enabled"
    filter {}
    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }
    transition {
      days          = 365
      storage_class = "DEEP_ARCHIVE"
    }
  }
}
