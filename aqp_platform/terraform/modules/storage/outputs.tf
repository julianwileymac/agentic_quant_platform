# NOTE: ``postgres_endpoint`` is declared in main.tf against the
# canonical resource names (aws_db_instance.pg, google_sql_database_instance.pg,
# azurerm_postgresql_flexible_server.pg). The earlier duplicate that
# referenced .aqp[0] is removed to silence the "Duplicate output
# definition" terraform-init error.

output "bucket_name" {
  description = "Canonical object-store bucket / container name."
  value = coalesce(
    try(aws_s3_bucket.aqp[0].bucket, null),
    try(google_storage_bucket.aqp[0].name, null),
    try(azurerm_storage_account.aqp[0].name, null),
    var.bucket_name,
  )
}

output "bucket_uri" {
  description = "Object-store URI suitable for AQP_S3_ENDPOINT_URL / equivalent."
  value = coalesce(
    try("s3://${aws_s3_bucket.aqp[0].bucket}", null),
    try("gs://${google_storage_bucket.aqp[0].name}", null),
    try("abfss://${azurerm_storage_account.aqp[0].name}.dfs.core.windows.net", null),
    "http://localhost:9000",
  )
}

# NOTE: ``redis_url`` lives in main.tf against the canonical resource
# names (.pg / .redis); the earlier duplicate referencing .aqp[0] is
# removed for the same reason as ``postgres_endpoint`` above.

output "tags" {
  value = local.base_tags
}
