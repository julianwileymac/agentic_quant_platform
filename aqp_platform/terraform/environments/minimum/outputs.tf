output "alb_dns_name" {
  value       = module.alb.dns_name
  description = "Public ALB hostname — point a CNAME / Cloudflare tunnel here."
}

output "alb_zone_id" {
  value = module.alb.zone_id
}

output "ecs_cluster_name" {
  value = module.ecs_fargate_admin.cluster_name
}

output "ecs_admin_service_id" {
  value = module.ecs_fargate_admin.service_arns["admin"]
}

output "cognito_user_pool_id" {
  value = module.cognito_userpool.user_pool_id
}

output "cognito_user_pool_endpoint" {
  value = module.cognito_userpool.user_pool_endpoint
}

output "cognito_shared_client_id" {
  value     = module.cognito_userpool.shared_client_id
  sensitive = true
}
