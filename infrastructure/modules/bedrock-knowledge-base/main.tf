###############################################################################
# modules/bedrock-knowledge-base — Bedrock KB + S3 source bucket.
#
# Wraps ``aws-ia/bedrock/aws`` with ``kb_storage_type = OPENSEARCH_SERVERLESS``
# so the KB writes its vector chunks into the upstream
# ``modules/opensearch-serverless`` collection. The S3 source bucket is
# operator-owned; documents land here (manually, via S3 PutObject, via the
# Dagster sandbox ingest tile, etc.) and the KB ingestion job indexes them.
#
# The eventual-consistency guard from the OSS module is honoured via the
# ``settle_resource_dep`` input — pass ``module.kb_oss.settle_resource_id``
# to ensure the IAM ``aoss:APIAccessAll`` grant has propagated before the
# KB creation kicks off.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

resource "aws_s3_bucket" "kb_source" {
  bucket = "${var.name_prefix}-kb-source-${var.environment}-${data.aws_caller_identity.current.account_id}"
  tags   = merge(var.tags, { Name = "${var.name_prefix}-kb-source-${var.environment}" })
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket_versioning" "kb_source" {
  bucket = aws_s3_bucket.kb_source.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "kb_source" {
  bucket = aws_s3_bucket.kb_source.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.kms_key_arn != null ? "aws:kms" : "AES256"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "kb_source" {
  bucket                  = aws_s3_bucket.kb_source.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

module "bedrock_kb" {
  source  = "aws-ia/bedrock/aws"
  version = ">= 0.0.20"

  create_kb              = true
  kb_name                = "${var.name_prefix}-kb-${var.environment}"
  kb_storage_type        = "OPENSEARCH_SERVERLESS"
  kb_oss_collection_arn  = var.oss_collection_arn
  kb_oss_collection_name = var.oss_collection_name
  kb_embedding_model_arn = var.embedding_model_arn

  create_default_kb_data_source = true
  kb_s3_data_source_bucket_arn  = aws_s3_bucket.kb_source.arn

  tags = var.tags
}

# Optional eventual-consistency dependency so the KB creation waits for
# the upstream IAM grant to propagate; consumers pass the OSS settle id.
resource "null_resource" "wait_for_settle" {
  count = var.settle_resource_dep != null ? 1 : 0
  triggers = {
    settle = var.settle_resource_dep
  }
}

resource "aws_ssm_parameter" "kb_id" {
  name  = "/aqp/${var.environment}/kb_knowledge_base_id"
  type  = "String"
  value = module.bedrock_kb.kb_id
  tags  = var.tags
}

resource "aws_ssm_parameter" "kb_source_bucket" {
  name  = "/aqp/${var.environment}/kb_source_bucket"
  type  = "String"
  value = aws_s3_bucket.kb_source.bucket
  tags  = var.tags
}
