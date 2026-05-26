###############################################################################
# envs/minimum — single-account, lowest-cost AQP footprint.
#
# Composes ONLY the infrastructure tier needed to run AQP-admin + the
# Bedrock LLM provider end-to-end on a single AWS account. Skips:
#
#   - EKS + Karpenter + ArgoCD     (no quant runtime tier; use ECS Fargate)
#   - MSK Kafka                    (no streaming for v1)
#   - observability-stack (Helm)   (no Prometheus stack; CloudWatch suffices)
#   - landing-zone / SCPs          (no AWS Organization in single-account mode)
#   - eso-bootstrap                (no in-cluster External Secrets; the
#                                   Fargate task role reads Secrets Manager
#                                   directly via the SDK)
#
# Output cost target: ~$140/month fixed + Bedrock token spend. See
# ``aqp_docs/docs/how-to/operations/aws-deploy.md`` for the cost ledger.
###############################################################################

###############################################################################
# 1. VPC — 2 AZs, single NAT, gateway endpoints free; interface endpoints
#    enabled so Bedrock + ECR + Secrets Manager + CloudWatch + SSM traffic
#    skips the NAT (cuts NAT bandwidth ~70%).
###############################################################################
module "vpc" {
  source             = "../../modules/vpc"
  name               = "aqp-min"
  cidr               = var.vpc_cidr
  azs_count          = 2
  single_nat_gateway = true
  tags = {
    aqp_io_component       = "network"
    aqp_io_data_classification = "internal"
  }
}

###############################################################################
# 2. ECR — keep only the repos the minimum deploy actually needs.
###############################################################################
module "ecr" {
  source       = "../../modules/ecr-repositories"
  kms_key_arn  = var.kms_key_arn
  account_id   = var.account_id
  region       = var.region
  enable_replication = false
  repositories = [
    "aqp-admin",
    "aqp-admin-frontend",
    "aqp-core",
  ]
  tags = { aqp_io_component = "ecr" }
}

###############################################################################
# 3. RDS Postgres — single-AZ ``db.t4g.medium`` is the cheapest line that
#    still ships gp3 + Performance Insights + IAM auth + automated backups.
###############################################################################
module "rds" {
  source         = "../../modules/rds-postgres"
  name           = "aqp-admin-min"
  vpc_id         = module.vpc.vpc_id
  subnet_ids     = module.vpc.private_subnet_ids
  kms_key_arn    = var.kms_key_arn
  instance_class = var.rds_instance_class
  multi_az       = var.rds_multi_az
  tags = { aqp_io_component = "database" }
}

###############################################################################
# 4. ElastiCache Redis — Celery broker + WS pub/sub. Inline (no module yet
#    in this repo for the smallest tier); single-node, in-transit + at-rest
#    encryption ON, automatic failover OFF (would force a second node).
###############################################################################
resource "aws_elasticache_subnet_group" "redis" {
  name       = "aqp-min-redis"
  subnet_ids = module.vpc.private_subnet_ids
  tags       = { aqp_io_component = "cache" }
}

resource "aws_security_group" "redis" {
  name        = "aqp-min-redis"
  description = "Redis 6379 from inside the VPC."
  vpc_id      = module.vpc.vpc_id
  ingress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { aqp_io_component = "cache" }
}

resource "random_password" "redis_auth" {
  length  = 32
  special = false
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "aqp-min-redis"
  description                = "AQP minimum Redis broker + WS pub/sub."
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = var.redis_node_type
  num_cache_clusters         = 1
  parameter_group_name       = "default.redis7"
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.redis.name
  security_group_ids         = [aws_security_group.redis.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = random_password.redis_auth.result
  kms_key_id                 = var.kms_key_arn
  apply_immediately          = false
  snapshot_retention_limit   = 3
  automatic_failover_enabled = false
  tags = { aqp_io_component = "cache" }
}

resource "aws_secretsmanager_secret" "redis_auth" {
  name        = "aqp/min/redis/auth_token"
  description = "Redis AUTH token for the aqp-min replication group."
  kms_key_id  = var.kms_key_arn
  tags        = { aqp_io_component = "cache" }
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "redis_auth" {
  secret_id     = aws_secretsmanager_secret.redis_auth.id
  secret_string = random_password.redis_auth.result
}

###############################################################################
# 5. IAM policy the ECS task role attaches to invoke Bedrock Claude Haiku
#    4.5 only. Long-term Bedrock API keys are NOT minted — boto3 chain only.
###############################################################################
resource "aws_iam_policy" "bedrock_invoke_haiku" {
  name        = "aqp-min-bedrock-invoke-haiku"
  description = "Allow bedrock:InvokeModel on Claude Haiku 4.5 only."
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "InvokeHaiku"
      Effect = "Allow"
      Action = [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
      ]
      Resource = [
        "arn:aws:bedrock:${var.region}::foundation-model/anthropic.claude-haiku-4-5-*",
      ]
    }]
  })
  tags = { aqp_io_component = "iam" }
}

###############################################################################
# 6. GitHub Actions deployer role for the minimum env.
###############################################################################
locals {
  github_repo_parts = split("/", var.github_deployer_repo)
}

module "github_actions_role" {
  source            = "../../modules/github-oidc"
  name              = "AqpGithubDeployerMinimum"
  oidc_provider_arn = var.github_oidc_provider_arn
  github_org        = local.github_repo_parts[0]
  github_repo       = local.github_repo_parts[1]
  ref_patterns = [
    "refs/heads/main",
    "refs/tags/v*-min*",
  ]
  policy_arns = [
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser",
    "arn:aws:iam::aws:policy/AmazonECS_FullAccess",
    "arn:aws:iam::aws:policy/AWSCloudFormationReadOnlyAccess",
  ]
  tags = { aqp_io_component = "iam" }
}

###############################################################################
# 7. SSM Parameter Store publishes — read by aqp_platform/terraform/
#    environments/minimum and by the application at runtime.
###############################################################################
resource "aws_ssm_parameter" "vpc_id" {
  name  = "/aqp/minimum/vpc_id"
  type  = "String"
  value = module.vpc.vpc_id
}

resource "aws_ssm_parameter" "private_subnet_ids" {
  name  = "/aqp/minimum/private_subnet_ids"
  type  = "StringList"
  value = join(",", module.vpc.private_subnet_ids)
}

resource "aws_ssm_parameter" "public_subnet_ids" {
  name  = "/aqp/minimum/public_subnet_ids"
  type  = "StringList"
  value = join(",", module.vpc.public_subnet_ids)
}

resource "aws_ssm_parameter" "ecr_registry" {
  name  = "/aqp/minimum/ecr_registry"
  type  = "String"
  value = "${var.account_id}.dkr.ecr.${var.region}.amazonaws.com"
}

resource "aws_ssm_parameter" "workload_kms_key_arn" {
  name  = "/aqp/minimum/workload_kms_key_arn"
  type  = "String"
  value = var.kms_key_arn
}

resource "aws_ssm_parameter" "rds_endpoint" {
  name  = "/aqp/minimum/rds_endpoint"
  type  = "String"
  value = module.rds.instance_endpoint
}

resource "aws_ssm_parameter" "redis_primary_endpoint" {
  name  = "/aqp/minimum/redis_primary_endpoint"
  type  = "String"
  value = aws_elasticache_replication_group.redis.primary_endpoint_address
}

resource "aws_ssm_parameter" "bedrock_invoke_policy_arn" {
  name  = "/aqp/minimum/bedrock_invoke_policy_arn"
  type  = "String"
  value = aws_iam_policy.bedrock_invoke_haiku.arn
}

###############################################################################
# 8. CloudWatch alarms — RDS + Redis + Bedrock. ALB + ECS alarms wire in
#    via the application-tier env (which knows the ARN suffixes).
###############################################################################
module "alarms" {
  source = "../../modules/cloudwatch-alarms"

  environment                = var.environment
  name_prefix                = "aqp"
  tags                       = { aqp_io_component = "observability" }
  rds_instance_id            = module.rds.instance_endpoint != null ? split(".", module.rds.instance_endpoint)[0] : null
  redis_replication_group_id = aws_elasticache_replication_group.redis.id
  bedrock_alarm_enabled      = true
}

resource "aws_ssm_parameter" "alarm_topic_arn" {
  name  = "/aqp/minimum/alarm_topic_arn_resolved"
  type  = "String"
  value = module.alarms.topic_arn
}
