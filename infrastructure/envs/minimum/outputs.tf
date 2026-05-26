output "vpc_id" {
  value = module.vpc.vpc_id
}

output "private_subnet_ids" {
  value = module.vpc.private_subnet_ids
}

output "public_subnet_ids" {
  value = module.vpc.public_subnet_ids
}

output "ecr_registry" {
  value = "${var.account_id}.dkr.ecr.${var.region}.amazonaws.com"
}

output "rds_endpoint" {
  value = module.rds.instance_endpoint
}

output "rds_security_group_id" {
  value = module.rds.security_group_id
}

output "redis_security_group_id" {
  value = aws_security_group.redis.id
}

output "redis_auth_secret_arn" {
  value     = aws_secretsmanager_secret.redis_auth.arn
  sensitive = true
}

output "redis_primary_endpoint" {
  value = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "bedrock_invoke_policy_arn" {
  value = aws_iam_policy.bedrock_invoke_haiku.arn
}

output "github_deployer_role_arn" {
  value = module.github_actions_role.role_arn
}

output "github_deployer_role_name" {
  value = module.github_actions_role.role_name
}
