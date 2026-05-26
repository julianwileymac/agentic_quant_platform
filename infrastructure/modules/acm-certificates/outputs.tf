output "certificate_arn" { value = aws_acm_certificate.this.arn }
output "validated_arn" { value = aws_acm_certificate_validation.this.certificate_arn }
