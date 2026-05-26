output "arn"                  { value = module.bedrock_kb.kb_arn }
output "name"                 { value = "${var.name_prefix}-kb-${var.environment}" }
output "kb_id"                { value = module.bedrock_kb.kb_id }
output "kb_source_bucket_arn" { value = aws_s3_bucket.kb_source.arn }
output "kb_source_bucket"     { value = aws_s3_bucket.kb_source.bucket }

output "ssm_parameters" {
  value = {
    kb_knowledge_base_id = aws_ssm_parameter.kb_id.name
    kb_source_bucket     = aws_ssm_parameter.kb_source_bucket.name
  }
}
