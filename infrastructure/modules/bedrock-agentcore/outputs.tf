output "arn" {
  value       = module.agentcore.runtime_arn
  description = "Primary AgentCore Runtime ARN; also published to SSM."
}

output "name" {
  value       = "${var.name_prefix}-runtime-${var.environment}"
  description = "Logical runtime name (matches SSM parameter naming)."
}

output "runtime_arn" {
  value = module.agentcore.runtime_arn
}

output "gateway_arn" {
  value = module.agentcore.gateway_arn
}

output "memory_id" {
  value = module.agentcore.memory_id
}

output "runtime_policy_arn" {
  value = aws_iam_policy.runtime_inline.arn
}

output "security_group_id" {
  value = aws_security_group.agentcore.id
}

output "ssm_parameters" {
  value = {
    runtime_arn        = aws_ssm_parameter.runtime_arn.name
    gateway_arn        = aws_ssm_parameter.gateway_arn.name
    memory_id          = aws_ssm_parameter.memory_id.name
    runtime_policy_arn = aws_ssm_parameter.runtime_policy_arn.name
  }
}
