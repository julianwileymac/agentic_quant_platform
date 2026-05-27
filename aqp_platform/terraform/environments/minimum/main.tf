###############################################################################
# environments/minimum — application tier (Cognito + ALB + ECS Fargate).
#
# Sits on top of ``infrastructure/envs/minimum`` (VPC + ECR + RDS + Redis +
# Bedrock invoke IAM). Composes the minimum subset of the Phase C modules:
#
#   - modules/cognito-userpool          (end-user auth)
#   - modules/alb                       (public HTTPS + Cognito-gated rules)
#   - modules/ecs-fargate-control-plane (admin BFF only — no AgentCore proxy)
#
# Deliberately SKIPS:
#
#   - modules/cloudfront                (use ALB DNS for v1)
#   - modules/bedrock-agentcore         (Bedrock LLM provider only)
#   - modules/bedrock-knowledge-base    (no KB until docs land in S3)
#   - modules/opensearch-serverless     (no vector store yet)
#   - modules/eventbridge-stepfunctions (no nightly backtests until strategies)
#   - EKS heritage composition          (no Celery worker tier)
###############################################################################

provider "aws" {
  region = var.region

  # Single-account minimum tier — see infrastructure/envs/minimum/providers.tf
  # for the rationale (no assume-role hop by default).
  dynamic "assume_role" {
    for_each = var.assume_role_arn != "" ? [1] : []
    content {
      role_arn     = var.assume_role_arn
      session_name = "aqp-terraform-minimum-app"
      external_id  = var.external_id != "" ? var.external_id : null
    }
  }

  default_tags {
    tags = local.common_tags
  }
}

locals {
  common_tags = {
    environment  = var.environment
    managed-by   = "terraform"
    component    = "aqp-minimum-app"
    organization = "wiley-tech"
  }
}

###############################################################################
# Pull every infrastructure-tier handle from SSM so this tree can stand
# alone (no remote-state read — matches the AGENTS rule 45 module contract).
###############################################################################
data "aws_ssm_parameter" "vpc_id"                 { name = "/aqp/minimum/vpc_id" }
data "aws_ssm_parameter" "private_subnet_ids"     { name = "/aqp/minimum/private_subnet_ids" }
data "aws_ssm_parameter" "public_subnet_ids"      { name = "/aqp/minimum/public_subnet_ids" }
data "aws_ssm_parameter" "ecr_registry"           { name = "/aqp/minimum/ecr_registry" }
data "aws_ssm_parameter" "workload_kms_key_arn"   { name = "/aqp/minimum/workload_kms_key_arn" }
data "aws_ssm_parameter" "rds_endpoint"           { name = "/aqp/minimum/rds_endpoint" }
data "aws_ssm_parameter" "redis_primary_endpoint" { name = "/aqp/minimum/redis_primary_endpoint" }
data "aws_ssm_parameter" "bedrock_invoke_policy_arn" {
  name = "/aqp/minimum/bedrock_invoke_policy_arn"
}

locals {
  vpc_id             = data.aws_ssm_parameter.vpc_id.value
  private_subnet_ids = split(",", data.aws_ssm_parameter.private_subnet_ids.value)
  public_subnet_ids  = split(",", data.aws_ssm_parameter.public_subnet_ids.value)
  ecr_registry       = data.aws_ssm_parameter.ecr_registry.value
  kms_key_arn        = data.aws_ssm_parameter.workload_kms_key_arn.value
  rds_endpoint       = data.aws_ssm_parameter.rds_endpoint.value
  redis_endpoint     = data.aws_ssm_parameter.redis_primary_endpoint.value
  bedrock_policy_arn = data.aws_ssm_parameter.bedrock_invoke_policy_arn.value
  admin_image        = "${local.ecr_registry}/aqp-admin:${var.admin_image_tag}"
}

###############################################################################
# 1. Cognito User Pool — end-user identity for the ALB.
###############################################################################
module "cognito_userpool" {
  source = "../../../../infrastructure/modules/cognito-userpool"

  environment        = var.environment
  name_prefix        = var.name_prefix
  tags               = local.common_tags
  vpc_id             = local.vpc_id
  private_subnet_ids = local.private_subnet_ids
  callback_urls      = var.callback_urls
  # Minimum tier: relax to OPTIONAL MFA so first-login UX is smooth.
  # Flip to "ON" once you wire the matching step-up flow.
  mfa_configuration  = "OPTIONAL"
}

###############################################################################
# 2. ALB — public HTTPS in front of the Fargate admin BFF.
###############################################################################
module "alb" {
  source = "../../../../infrastructure/modules/alb"

  environment        = var.environment
  name_prefix        = var.name_prefix
  tags               = local.common_tags
  vpc_id             = local.vpc_id
  public_subnet_ids  = local.public_subnet_ids
  private_subnet_ids = local.private_subnet_ids
  certificate_arn    = var.acm_certificate_arn_alb
  access_logs_bucket = var.alb_access_logs_bucket

  cognito_user_pool_arn       = module.cognito_userpool.user_pool_arn
  cognito_user_pool_client_id = module.cognito_userpool.shared_client_id
  cognito_user_pool_domain    = module.cognito_userpool.user_pool_domain

  # Override the default 2-service map: only the admin tier exists in
  # the minimum environment (no AgentCore proxy).
  target_groups = {
    admin = {
      port              = 8000
      protocol          = "HTTP"
      health_check_path = "/health"
    }
  }
  default_target_group_key = "admin"

  cognito_protected_paths = {
    admin = {
      priority         = 100
      path_patterns    = ["/admin/*", "/manage/*"]
      target_group_key = "admin"
    }
  }
}

###############################################################################
# 3. ECS Fargate cluster + the single ``aqp-admin`` service.
###############################################################################
module "ecs_fargate_admin" {
  source = "../../../../infrastructure/modules/ecs-fargate-control-plane"

  environment           = var.environment
  name_prefix           = var.name_prefix
  tags                  = local.common_tags
  vpc_id                = local.vpc_id
  private_subnet_ids    = local.private_subnet_ids
  kms_key_arn           = local.kms_key_arn
  alb_security_group_id = module.alb.security_group_id

  services = {
    admin = {
      image                 = local.admin_image
      cpu                   = 1024
      memory                = 2048
      desired_count         = 1
      ports                 = [8000]
      cpu_architecture      = "ARM64"
      task_role_policy_arns = [local.bedrock_policy_arn]
      secrets               = []
      alb_target_group_arn  = module.alb.target_group_arns["admin"]
    }
  }
}

###############################################################################
# 4. SSM publishes — read by the application at runtime + by smoke tests.
###############################################################################
resource "aws_ssm_parameter" "alb_dns_name" {
  name  = "/aqp/${var.environment}/alb_dns_name"
  type  = "String"
  value = module.alb.dns_name
}

resource "aws_ssm_parameter" "ecs_cluster_name" {
  name  = "/aqp/${var.environment}/ecs_cluster_name"
  type  = "String"
  value = module.ecs_fargate_admin.cluster_name
}

resource "aws_ssm_parameter" "cognito_user_pool_endpoint" {
  name  = "/aqp/${var.environment}/cognito_user_pool_endpoint"
  type  = "String"
  value = module.cognito_userpool.user_pool_endpoint
}
