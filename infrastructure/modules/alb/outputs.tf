output "arn"  { value = module.alb.arn }
output "name" { value = module.alb.name }

output "dns_name" { value = module.alb.dns_name }
output "zone_id"  { value = module.alb.zone_id }

output "security_group_id" { value = aws_security_group.alb.id }

output "target_group_arns" {
  value       = { for k, tg in aws_lb_target_group.default : k => tg.arn }
  description = "Map of target_group key -> ARN; ECS service definitions wire to these."
}

output "https_listener_arn" { value = aws_lb_listener.https.arn }

output "ssm_parameters" {
  value = {
    alb_dns_name = aws_ssm_parameter.alb_dns_name.name
    alb_arn      = aws_ssm_parameter.alb_arn.name
    alb_zone_id  = aws_ssm_parameter.alb_zone_id.name
  }
}
