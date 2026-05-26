output "arn"  { value = module.collection.collection_arn }
output "name" { value = module.collection.collection_name }

output "collection_arn"  { value = module.collection.collection_arn }
output "collection_name" { value = module.collection.collection_name }

output "settle_resource_id" {
  value       = time_sleep.settle.id
  description = "Reference for consumer depends_on chains."
}

output "ssm_parameters" {
  value = {
    collection_arn  = aws_ssm_parameter.collection_arn.name
    collection_name = aws_ssm_parameter.collection_name.name
  }
}
