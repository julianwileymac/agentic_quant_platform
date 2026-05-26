###############################################################################
# modules/bedrock-agentcore — Amazon Bedrock AgentCore Runtime + Memory + Gateway.
#
# Wraps the official ``aws-ia/agentcore/aws`` Terraform module pinned to
# ``0.0.2`` (the Registry's current release). The agent runtime image MUST be
# ARM64-only per the AgentCore documentation; build via
# ``docker buildx --platform=linux/arm64`` and push to the per-account ECR
# repo provisioned by ``modules/ecr-repositories``.
#
# Provider pin: the AgentCore resource types
# (``aws_bedrockagentcore_agent_runtime``, ``_memory``, ``_gateway``) require
# ``hashicorp/aws ~> 6.21`` (the minimum tested version per the AgentCore
# Terraform docs). The root composition (``infrastructure/envs/*/main.tf``)
# upgrades the provider when this module is included.
#
# Cross-module wiring contract: every important ARN/id is mirrored into
# SSM Parameter Store at ``/aqp/${var.environment}/agentcore_*`` so the
# in-monolith ``AgentRuntime.delegated`` invocation path resolves the
# runtime without remote-state reads.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.21" }
  }
}

module "agentcore" {
  source  = "aws-ia/agentcore/aws"
  version = "0.0.2"

  create_runtime                 = true
  runtime_name                   = "${var.name_prefix}-runtime-${var.environment}"
  runtime_network_mode           = "VPC"
  runtime_vpc_subnet_ids         = var.private_subnet_ids
  runtime_vpc_security_group_ids = [aws_security_group.agentcore.id]
  runtime_image_uri              = var.runtime_image_uri

  create_memory                = true
  memory_name                  = "${var.name_prefix}-memory-${var.environment}"
  memory_event_expiry_duration = var.memory_event_expiry_days

  create_gateway          = true
  gateway_name            = "${var.name_prefix}-gateway-${var.environment}"
  gateway_authorizer_type = var.gateway_authorizer_type

  tags = merge(var.tags, { Name = "${var.name_prefix}-agentcore-${var.environment}" })
}

resource "aws_security_group" "agentcore" {
  name        = "${var.name_prefix}-agentcore-${var.environment}"
  description = "AgentCore Runtime egress — Bedrock + STS + Secrets Manager + KMS."
  vpc_id      = var.vpc_id

  egress {
    description = "HTTPS to AWS service endpoints."
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.tags
}

###############################################################################
# Least-privilege execution role (blueprint §8.3).
###############################################################################

data "aws_iam_policy_document" "runtime_inline" {
  statement {
    sid     = "InvokeAllowedModels"
    effect  = "Allow"
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = var.allowed_model_arns
  }

  dynamic "statement" {
    for_each = length(var.broker_secret_arns) > 0 ? [1] : []
    content {
      sid       = "ReadBrokerSecrets"
      effect    = "Allow"
      actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
      resources = var.broker_secret_arns
    }
  }

  dynamic "statement" {
    for_each = var.kb_source_bucket_arn != null ? [1] : []
    content {
      sid       = "ReadKBSource"
      effect    = "Allow"
      actions   = ["s3:GetObject", "s3:ListBucket"]
      resources = [
        var.kb_source_bucket_arn,
        "${var.kb_source_bucket_arn}/*",
      ]
    }
  }

  statement {
    sid       = "EmitLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:CreateLogGroup"]
    resources = ["arn:aws:logs:*:*:log-group:/aws/bedrock-agentcore/${var.name_prefix}-${var.environment}:*"]
  }
}

resource "aws_iam_policy" "runtime_inline" {
  name        = "${var.name_prefix}-agentcore-runtime-${var.environment}"
  description = "Least-privilege Bedrock AgentCore runtime policy."
  policy      = data.aws_iam_policy_document.runtime_inline.json
  tags        = var.tags
}

###############################################################################
# SSM Parameter Store outputs — module-contract per the blueprint.
###############################################################################

resource "aws_ssm_parameter" "runtime_arn" {
  name  = "/aqp/${var.environment}/agentcore_runtime_arn"
  type  = "String"
  value = module.agentcore.runtime_arn
  tags  = var.tags
}

resource "aws_ssm_parameter" "gateway_arn" {
  name  = "/aqp/${var.environment}/agentcore_gateway_arn"
  type  = "String"
  value = module.agentcore.gateway_arn
  tags  = var.tags
}

resource "aws_ssm_parameter" "memory_id" {
  name  = "/aqp/${var.environment}/agentcore_memory_id"
  type  = "String"
  value = module.agentcore.memory_id
  tags  = var.tags
}

resource "aws_ssm_parameter" "runtime_policy_arn" {
  name  = "/aqp/${var.environment}/agentcore_runtime_policy_arn"
  type  = "String"
  value = aws_iam_policy.runtime_inline.arn
  tags  = var.tags
}
