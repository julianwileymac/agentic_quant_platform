output "arn"  { value = aws_ecs_cluster.this.arn }
output "name" { value = aws_ecs_cluster.this.name }

output "cluster_arn"  { value = aws_ecs_cluster.this.arn }
output "cluster_name" { value = aws_ecs_cluster.this.name }

output "task_security_group_id" { value = aws_security_group.tasks.id }
output "execution_role_arn"     { value = aws_iam_role.execution.arn }

output "service_arns" {
  value = { for k, svc in aws_ecs_service.this : k => svc.id }
}

output "task_role_arns" {
  value = { for k, role in aws_iam_role.task : k => role.arn }
}

output "log_group_names" {
  value = { for k, lg in aws_cloudwatch_log_group.service : k => lg.name }
}

output "ssm_parameters" {
  value = {
    cluster_name  = aws_ssm_parameter.cluster_name.name
    cluster_arn   = aws_ssm_parameter.cluster_arn.name
    service_names = aws_ssm_parameter.service_names.name
  }
}
