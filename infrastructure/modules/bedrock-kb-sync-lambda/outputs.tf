output "arn"  { value = aws_lambda_function.kb_sync.arn }
output "name" { value = aws_lambda_function.kb_sync.function_name }

output "lambda_arn"   { value = aws_lambda_function.kb_sync.arn }
output "role_arn"     { value = aws_iam_role.lambda.arn }
output "log_group"    { value = aws_cloudwatch_log_group.lambda.name }

output "ssm_parameters" {
  value = {
    kb_sync_lambda_arn = aws_ssm_parameter.lambda_arn.name
  }
}
