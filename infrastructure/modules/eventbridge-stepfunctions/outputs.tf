output "arn"  { value = aws_sfn_state_machine.nightly_backtest.arn }
output "name" { value = aws_sfn_state_machine.nightly_backtest.name }

output "state_machine_arn"  { value = aws_sfn_state_machine.nightly_backtest.arn }
output "nightly_cron_rule_arn" { value = aws_cloudwatch_event_rule.nightly_cron.arn }

output "kb_sync_rule_arn" {
  value = try(aws_cloudwatch_event_rule.kb_sync[0].arn, null)
}

output "ssm_parameters" {
  value = {
    nightly_sfn_arn   = aws_ssm_parameter.sfn_arn.name
    nightly_rule_arn  = aws_ssm_parameter.nightly_rule_arn.name
  }
}
