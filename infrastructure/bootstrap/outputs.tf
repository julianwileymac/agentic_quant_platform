output "kms_key_arn" {
  description = "KMS customer-managed key ARN for tfstate + audit-archive encryption."
  value       = aws_kms_key.tfstate.arn
}

output "tfstate_bucket" {
  description = "Remote-state S3 bucket name."
  value       = aws_s3_bucket.tfstate.bucket
}

output "tfstate_lock_legacy_table" {
  description = "DynamoDB legacy lock table (reserved; not used in normal operation)."
  value       = aws_dynamodb_table.tfstate_lock_legacy.name
}

output "github_oidc_provider_arn" {
  description = "GitHub Actions OIDC provider ARN."
  value       = aws_iam_openid_connect_provider.github_actions.arn
}

output "account_id" {
  description = "AWS account id this stack was applied into."
  value       = data.aws_caller_identity.current.account_id
}
