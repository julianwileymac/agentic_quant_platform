output "account_id" { value = aws_organizations_account.this.id }
output "account_arn" { value = aws_organizations_account.this.arn }
output "execution_role_arn" {
  value = "arn:aws:iam::${aws_organizations_account.this.id}:role/AqpTerraformExecutionRole"
}
output "permissions_boundary_arn" {
  value = aws_iam_policy.terraform_permissions_boundary.arn
}
