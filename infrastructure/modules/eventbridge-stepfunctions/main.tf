###############################################################################
# modules/eventbridge-stepfunctions — nightly orchestration + KB sync triggers.
#
# Three primary outputs:
#
# 1. A Step Function (``aqp-nightly-backtest-${env}``) that fan-runs every
#    strategy listed in ``configs/strategies/`` and posts results back to
#    the AQP API.
# 2. An EventBridge cron rule (00 21 * * MON-FRI UTC = 16:00 ET; tunable)
#    that triggers the Step Function on weekdays after the US session
#    closes.
# 3. A second EventBridge rule listening for S3 ObjectCreated events on
#    the KB source bucket; the matched events route to a Lambda that
#    starts a Bedrock KB ingestion job (lazy re-index when operators
#    drop new research docs).
#
# The Step Function definition is parameter-driven via
# ``var.state_machine_definition_json``; the consumer composition emits
# the JSON via a ``stepfunctions_state_machine`` builder (or a separate
# script that resolves strategy names from the latest
# ``configs/strategies/`` listing).
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

###############################################################################
# IAM — Step Function execution role + Lambda execution role.
###############################################################################

data "aws_iam_policy_document" "sfn_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${var.name_prefix}-nightly-sfn-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.sfn_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "sfn_inline" {
  statement {
    sid       = "InvokeBackendLambda"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = var.backend_lambda_arns
  }
  statement {
    sid       = "EmitLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:CreateLogGroup"]
    resources = ["arn:aws:logs:*:*:log-group:/aws/vendedlogs/states/*"]
  }
  statement {
    sid       = "CloudWatchLogsDelivery"
    effect    = "Allow"
    actions   = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "sfn_inline" {
  name   = "${var.name_prefix}-nightly-sfn-inline-${var.environment}"
  role   = aws_iam_role.sfn.name
  policy = data.aws_iam_policy_document.sfn_inline.json
}

resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/vendedlogs/states/${var.name_prefix}-nightly-${var.environment}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn
  tags              = var.tags
}

resource "aws_sfn_state_machine" "nightly_backtest" {
  name     = "${var.name_prefix}-nightly-backtest-${var.environment}"
  role_arn = aws_iam_role.sfn.arn
  type     = "STANDARD"
  definition = var.state_machine_definition_json

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }

  tags = var.tags
}

###############################################################################
# EventBridge — nightly cron + S3 KB sync triggers.
###############################################################################

resource "aws_cloudwatch_event_rule" "nightly_cron" {
  name                = "${var.name_prefix}-nightly-${var.environment}"
  description         = "Nightly Step Function trigger (US weekdays after close)."
  schedule_expression = var.nightly_cron_expression
  state               = var.environment == "prod" ? "ENABLED" : "DISABLED"
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "nightly_cron" {
  rule     = aws_cloudwatch_event_rule.nightly_cron.name
  arn      = aws_sfn_state_machine.nightly_backtest.arn
  role_arn = aws_iam_role.events_target.arn
}

data "aws_iam_policy_document" "events_target_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "events_target" {
  name               = "${var.name_prefix}-events-target-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.events_target_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "events_target_inline" {
  statement {
    sid       = "StartSFN"
    effect    = "Allow"
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.nightly_backtest.arn]
  }
}

resource "aws_iam_role_policy" "events_target_inline" {
  name   = "${var.name_prefix}-events-target-inline-${var.environment}"
  role   = aws_iam_role.events_target.name
  policy = data.aws_iam_policy_document.events_target_inline.json
}

###############################################################################
# S3 ObjectCreated -> Bedrock KB ingestion trigger.
###############################################################################

resource "aws_cloudwatch_event_rule" "kb_sync" {
  count       = var.kb_source_bucket_name != null ? 1 : 0
  name        = "${var.name_prefix}-kb-sync-${var.environment}"
  description = "Lazy re-index of the Bedrock KB on every S3 PutObject."
  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = {
        name = [var.kb_source_bucket_name]
      }
    }
  })
  state = "ENABLED"
  tags  = var.tags
}

resource "aws_cloudwatch_event_target" "kb_sync" {
  count = var.kb_source_bucket_name != null && var.kb_sync_lambda_arn != null ? 1 : 0
  rule  = aws_cloudwatch_event_rule.kb_sync[0].name
  arn   = var.kb_sync_lambda_arn
}

resource "aws_lambda_permission" "events_kb_sync" {
  count         = var.kb_source_bucket_name != null && var.kb_sync_lambda_arn != null ? 1 : 0
  statement_id  = "AllowEventsToInvokeKbSync"
  action        = "lambda:InvokeFunction"
  function_name = var.kb_sync_lambda_arn
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.kb_sync[0].arn
}

resource "aws_ssm_parameter" "sfn_arn" {
  name  = "/aqp/${var.environment}/nightly_sfn_arn"
  type  = "String"
  value = aws_sfn_state_machine.nightly_backtest.arn
  tags  = var.tags
}

resource "aws_ssm_parameter" "nightly_rule_arn" {
  name  = "/aqp/${var.environment}/nightly_rule_arn"
  type  = "String"
  value = aws_cloudwatch_event_rule.nightly_cron.arn
  tags  = var.tags
}
