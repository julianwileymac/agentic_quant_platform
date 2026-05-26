###############################################################################
# Live trading environment — AWS hybrid topology.
#
# Composition order (per blueprint §13.3):
#   1. networking      — VPC + private/public subnets + endpoints
#   2. secrets         — Cognito User Pool (consumed by ALB OIDC)
#   3. cognito_userpool — User Pool + shared SPA client + SSM publish
#   4. alb             — public ALB + Cognito-gated listener rules
#   5. ecs_fargate_admin — admin BFF + AgentCore reverse proxy (Fargate)
#   6. opensearch_serverless — VECTORSEARCH collection for Bedrock KB
#   7. bedrock_kb      — Bedrock KB + S3 source bucket
#   8. bedrock_agentcore — AgentCore Runtime + Memory + Gateway
#   9. cloudfront      — CDN in front of ALB for admin/agentcore surface
#  10. eventbridge_sfn — nightly backtest + KB sync triggers
#  11. aqp (existing)  — EKS Karpenter quant runtime + storage + agents
#
# EKS Karpenter continues to host the quant runtime workloads (Celery
# workers, Iceberg writers, MLflow, Strimzi, Flink) per the operator's
# hybrid topology decision. ECS Fargate owns the admin BFF + AgentCore
# reverse proxy slice only.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    # Pinned ``~> 6.21`` per the Bedrock AgentCore provider requirement
    # (the aws_bedrockagentcore_* resource types were introduced in 6.x).
    aws        = { source = "hashicorp/aws", version = "~> 6.21" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.32" }
    helm       = { source = "hashicorp/helm", version = "~> 2.16" }
    random     = { source = "hashicorp/random", version = "~> 3.6" }
    time       = { source = "hashicorp/time", version = "~> 0.12" }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = local.common_tags
  }
}

# Second AWS provider alias targeting us-east-1 — CloudFront requires
# its ACM cert to live in us-east-1 regardless of the workload region.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags {
    tags = local.common_tags
  }
}

provider "kubernetes" {
  config_path = "~/.kube/config"
}

provider "helm" {
  kubernetes {
    config_path = "~/.kube/config"
  }
}

###############################################################################
# Inputs — overridden via terraform.tfvars / TF_VAR_* env vars.
###############################################################################

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "live"
}

variable "name_prefix" {
  type    = string
  default = "aqp"
}

variable "vpc_cidr" {
  type    = string
  default = "10.30.0.0/16"
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "Public subnets for the ALB (resolved from infrastructure/envs/{env} outputs)."
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnets for Fargate + AgentCore (resolved from infrastructure/envs/{env} outputs)."
}

variable "vpc_id" {
  type        = string
  description = "VPC id (resolved from infrastructure/envs/{env} outputs)."
}

variable "workload_kms_key_arn" {
  type        = string
  description = "Per-env workload CMK ARN (provisioned by infrastructure/bootstrap/)."
}

variable "acm_certificate_arn_alb" {
  type        = string
  description = "ACM cert ARN for the ALB HTTPS listener (regional)."
}

variable "acm_certificate_arn_cloudfront" {
  type        = string
  description = "ACM cert ARN for the CloudFront distribution (us-east-1 required)."
}

variable "agentcore_runtime_image_uri" {
  type        = string
  description = "ARM64 image URI for the AgentCore Runtime container (from ECR)."
}

variable "cloudfront_aliases" {
  type    = list(string)
  default = ["admin.aqp.fund", "agentcore.aqp.fund"]
}

variable "alb_access_logs_bucket" {
  type    = string
  default = null
}

variable "cloudfront_origin_secret" {
  type      = string
  sensitive = true
}

variable "callback_urls" {
  type    = list(string)
  default = ["https://admin.aqp.fund/oauth/callback"]
}

variable "nightly_state_machine_definition_json" {
  type        = string
  default     = "{\"StartAt\": \"NoOp\", \"States\": {\"NoOp\": {\"Type\": \"Succeed\"}}}"
  description = "Step Function definition JSON — render from configs/strategies/."
}

locals {
  common_tags = {
    environment  = var.environment
    managed-by   = "terraform"
    component    = "aqp-aws-live"
    organization = "wiley-tech"
  }
}

###############################################################################
# 1. cognito_userpool — end-user identity for the ALB.
###############################################################################

module "cognito_userpool" {
  source = "../../../../infrastructure/modules/cognito-userpool"

  environment        = var.environment
  name_prefix        = var.name_prefix
  tags               = local.common_tags
  vpc_id             = var.vpc_id
  private_subnet_ids = var.private_subnet_ids
  callback_urls      = var.callback_urls
}

###############################################################################
# 2. alb — public ALB + Cognito-gated listener.
###############################################################################

module "alb" {
  source = "../../../../infrastructure/modules/alb"

  environment        = var.environment
  name_prefix        = var.name_prefix
  tags               = local.common_tags
  vpc_id             = var.vpc_id
  public_subnet_ids  = var.public_subnet_ids
  private_subnet_ids = var.private_subnet_ids
  certificate_arn    = var.acm_certificate_arn_alb
  access_logs_bucket = var.alb_access_logs_bucket

  cognito_user_pool_arn       = module.cognito_userpool.user_pool_arn
  cognito_user_pool_client_id = module.cognito_userpool.shared_client_id
  cognito_user_pool_domain    = module.cognito_userpool.user_pool_domain
}

###############################################################################
# 3. ecs_fargate_admin — admin BFF + AgentCore reverse proxy.
###############################################################################

module "ecs_fargate_admin" {
  source = "../../../../infrastructure/modules/ecs-fargate-control-plane"

  environment           = var.environment
  name_prefix           = var.name_prefix
  tags                  = local.common_tags
  vpc_id                = var.vpc_id
  private_subnet_ids    = var.private_subnet_ids
  kms_key_arn           = var.workload_kms_key_arn
  alb_security_group_id = module.alb.security_group_id
  # The default services map ships placeholder images; the operator
  # overrides via terraform.tfvars to point at the freshly-built ECR
  # tags (image URIs come from the build-publish.yml workflow).
}

###############################################################################
# 4. opensearch_serverless + bedrock_kb — Bedrock Knowledge Base.
###############################################################################

module "opensearch_serverless" {
  source = "../../../../infrastructure/modules/opensearch-serverless"

  environment = var.environment
  name_prefix = var.name_prefix
  tags        = local.common_tags
  kms_key_arn = var.workload_kms_key_arn
}

module "bedrock_kb" {
  source = "../../../../infrastructure/modules/bedrock-knowledge-base"

  environment         = var.environment
  name_prefix         = var.name_prefix
  tags                = local.common_tags
  kms_key_arn         = var.workload_kms_key_arn
  oss_collection_arn  = module.opensearch_serverless.collection_arn
  oss_collection_name = module.opensearch_serverless.collection_name
  settle_resource_dep = module.opensearch_serverless.settle_resource_id
}

###############################################################################
# 5. bedrock_agentcore — Runtime + Memory + Gateway.
###############################################################################

module "bedrock_agentcore" {
  source = "../../../../infrastructure/modules/bedrock-agentcore"

  environment          = var.environment
  name_prefix          = var.name_prefix
  tags                 = local.common_tags
  vpc_id               = var.vpc_id
  private_subnet_ids   = var.private_subnet_ids
  kms_key_arn          = var.workload_kms_key_arn
  runtime_image_uri    = var.agentcore_runtime_image_uri
  kb_source_bucket_arn = module.bedrock_kb.kb_source_bucket_arn
}

###############################################################################
# 6. cloudfront — CDN in front of the ALB (admin + AgentCore proxy edge).
#
# CloudFront cert MUST live in us-east-1 regardless of the workload region.
# The provider alias ``us_east_1`` declared above handles that requirement.
###############################################################################

module "cloudfront" {
  source = "../../../../infrastructure/modules/cloudfront"

  environment                = var.environment
  name_prefix                = var.name_prefix
  tags                       = local.common_tags
  alb_dns_name               = module.alb.dns_name
  aliases                    = var.cloudfront_aliases
  acm_certificate_arn        = var.acm_certificate_arn_cloudfront
  origin_secret_header_value = var.cloudfront_origin_secret

  providers = {
    aws = aws.us_east_1
  }
}

###############################################################################
# 7. kb_sync_lambda — lazy Bedrock KB re-ingestion on every S3 PutObject.
###############################################################################

module "kb_sync_lambda" {
  source = "../../../../infrastructure/modules/bedrock-kb-sync-lambda"

  environment       = var.environment
  name_prefix       = var.name_prefix
  tags              = local.common_tags
  kms_key_arn       = var.workload_kms_key_arn
  knowledge_base_id = module.bedrock_kb.kb_id
  data_source_id    = "default"  # the aws-ia/bedrock/aws module creates a
                                 # data source named ``default`` when
                                 # create_default_kb_data_source=true
  source_bucket_arn = module.bedrock_kb.kb_source_bucket_arn
}

###############################################################################
# 8. eventbridge_sfn — nightly backtest cron + S3 -> Lambda KB sync wiring.
###############################################################################

module "eventbridge_sfn" {
  source = "../../../../infrastructure/modules/eventbridge-stepfunctions"

  environment                   = var.environment
  name_prefix                   = var.name_prefix
  tags                          = local.common_tags
  kms_key_arn                   = var.workload_kms_key_arn
  state_machine_definition_json = var.nightly_state_machine_definition_json
  kb_source_bucket_name         = module.bedrock_kb.kb_source_bucket
  kb_sync_lambda_arn            = module.kb_sync_lambda.lambda_arn
}

###############################################################################
# 8. aqp (existing core composition) — EKS Karpenter quant runtime.
#
# The existing ``../../`` module is the heritage AQP composition (storage,
# pipeline, faas, agents, kubernetes, secrets). EKS Karpenter continues to
# host the quant runtime workloads (Celery workers, Iceberg writers,
# MLflow, Strimzi, Flink) per the hybrid topology decision.
###############################################################################

module "aqp" {
  source            = "../../"
  cloud_provider    = "aws"
  environment       = "live"
  organization_slug = "wiley-tech"
  workspace_slug    = "main"
  app_version       = "latest"
  aws_region        = var.aws_region
}

###############################################################################
# Outputs — published to the topology fallback chain via SSM.
###############################################################################

output "namespaces"            { value = module.aqp.namespaces }
output "cluster_endpoint"      { value = module.aqp.cluster_endpoint }
output "registry_url"          { value = module.aqp.registry_url }
output "object_store_url"      { value = module.aqp.object_store_url }
output "redis_url"             { value = module.aqp.redis_url }
output "ingress_host"          { value = module.aqp.ingress_host }

output "alb_dns_name"          { value = module.alb.dns_name }
output "cloudfront_domain"     { value = module.cloudfront.domain_name }
output "agentcore_runtime_arn" { value = module.bedrock_agentcore.runtime_arn }
output "agentcore_gateway_arn" { value = module.bedrock_agentcore.gateway_arn }
output "kb_collection_arn"     { value = module.opensearch_serverless.collection_arn }
output "kb_id"                 { value = module.bedrock_kb.kb_id }
output "ecs_cluster_name"      { value = module.ecs_fargate_admin.cluster_name }
output "cognito_user_pool_id"  { value = module.cognito_userpool.user_pool_id }
output "nightly_sfn_arn"       { value = module.eventbridge_sfn.state_machine_arn }
