output "arn" {
  value = local.topic_arn
}

output "name" {
  value = "${var.name_prefix}-alarms-${var.environment}"
}

output "topic_arn" {
  value = local.topic_arn
}

output "dashboard_name" {
  value = aws_cloudwatch_dashboard.main.dashboard_name
}

output "ssm_parameters" {
  value = {
    alarm_topic_arn = aws_ssm_parameter.topic_arn.name
  }
}
