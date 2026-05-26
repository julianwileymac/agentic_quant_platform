output "arn"             { value = aws_cloudfront_distribution.this.arn }
output "name"            { value = "${var.name_prefix}-cf-${var.environment}" }
output "distribution_id" { value = aws_cloudfront_distribution.this.id }
output "domain_name"     { value = aws_cloudfront_distribution.this.domain_name }
output "hosted_zone_id"  { value = aws_cloudfront_distribution.this.hosted_zone_id }

output "ssm_parameters" {
  value = {
    cloudfront_domain          = aws_ssm_parameter.distribution_domain.name
    cloudfront_distribution_id = aws_ssm_parameter.distribution_id.name
  }
}
