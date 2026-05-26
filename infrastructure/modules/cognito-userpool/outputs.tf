output "arn"  { value = aws_cognito_user_pool.this.arn }
output "name" { value = aws_cognito_user_pool.this.name }

output "user_pool_id"         { value = aws_cognito_user_pool.this.id }
output "user_pool_arn"        { value = aws_cognito_user_pool.this.arn }
output "user_pool_endpoint"   { value = "https://${aws_cognito_user_pool.this.endpoint}" }
output "user_pool_domain"     { value = aws_cognito_user_pool_domain.this.domain }
output "shared_client_id"     { value = aws_cognito_user_pool_client.shared.id }

output "shared_client_secret" {
  value     = aws_cognito_user_pool_client.shared.client_secret
  sensitive = true
}

output "identity_pool_id" {
  value = try(aws_cognito_identity_pool.this[0].id, null)
}

output "ssm_parameters" {
  value = {
    user_pool_id         = aws_ssm_parameter.user_pool_id.name
    user_pool_arn        = aws_ssm_parameter.user_pool_arn.name
    user_pool_endpoint   = aws_ssm_parameter.user_pool_endpoint.name
    user_pool_domain     = aws_ssm_parameter.user_pool_domain.name
    shared_client_id     = aws_ssm_parameter.shared_client_id.name
    shared_client_secret = aws_ssm_parameter.shared_client_secret.name
  }
}
