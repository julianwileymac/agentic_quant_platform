###############################################################################
# modules/bedrock-kb-sync-lambda — lazy Bedrock KB re-ingestion on S3 events.
#
# Wires the EventBridge ``Object Created`` rule from
# modules/eventbridge-stepfunctions to a Python Lambda that calls
# ``bedrock-agent:StartIngestionJob`` for the Knowledge Base. The
# Lambda is idempotent — duplicate events for the same KB result in
# the most recent job winning; we don't fan out one ingestion per
# object (StartIngestionJob walks the whole data source).
#
# Inputs:
#  - knowledge_base_id      — Bedrock KB id (from modules/bedrock-knowledge-base)
#  - data_source_id         — the KB's S3 data source id
#  - source_bucket_arn      — for IAM (HeadObject + ListBucket on the source)
#
# Output the EventBridge module consumes: ``lambda_arn``.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.70" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
  }
}

variable "environment"        { type = string }
variable "name_prefix"        { type = string, default = "aqp" }
variable "tags"               { type = map(string), default = {} }
variable "knowledge_base_id"  { type = string }
variable "data_source_id"     { type = string }
variable "source_bucket_arn"  { type = string }
variable "kms_key_arn"        { type = string, default = null }
variable "log_retention_days" { type = number, default = 30 }

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

###############################################################################
# Package the Lambda source from this module's ``lambda/`` directory.
###############################################################################
data "archive_file" "kb_sync" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/.build/kb_sync.zip"
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.name_prefix}-kb-sync-${var.environment}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn
  tags              = var.tags
}

###############################################################################
# IAM — minimal: bedrock-agent:StartIngestionJob + S3 read on the source.
###############################################################################
data "aws_iam_policy_document" "lambda_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.name_prefix}-kb-sync-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "lambda_inline" {
  statement {
    sid       = "StartIngestion"
    effect    = "Allow"
    actions   = ["bedrock-agent:StartIngestionJob"]
    resources = [
      "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:knowledge-base/${var.knowledge_base_id}",
      "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:knowledge-base/${var.knowledge_base_id}/data-source/${var.data_source_id}",
    ]
  }
  statement {
    sid    = "ReadSourceBucket"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
      "s3:HeadObject",
    ]
    resources = [
      var.source_bucket_arn,
      "${var.source_bucket_arn}/*",
    ]
  }
  statement {
    sid    = "EmitLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }
}

resource "aws_iam_role_policy" "lambda_inline" {
  name   = "${var.name_prefix}-kb-sync-inline-${var.environment}"
  role   = aws_iam_role.lambda.name
  policy = data.aws_iam_policy_document.lambda_inline.json
}

resource "aws_lambda_function" "kb_sync" {
  function_name    = "${var.name_prefix}-kb-sync-${var.environment}"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.kb_sync.output_path
  source_code_hash = data.archive_file.kb_sync.output_base64sha256
  memory_size      = 256
  timeout          = 60

  environment {
    variables = {
      KB_ID          = var.knowledge_base_id
      DATA_SOURCE_ID = var.data_source_id
      AQP_ENV        = var.environment
    }
  }

  reserved_concurrent_executions = 5
  publish                        = true

  depends_on = [
    aws_iam_role_policy.lambda_inline,
    aws_cloudwatch_log_group.lambda,
  ]

  tags = var.tags
}

resource "aws_ssm_parameter" "lambda_arn" {
  name  = "/aqp/${var.environment}/kb_sync_lambda_arn"
  type  = "String"
  value = aws_lambda_function.kb_sync.arn
  tags  = var.tags
}
