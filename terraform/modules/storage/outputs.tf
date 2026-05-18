output "postgres_endpoint" {
  description = "Postgres connection endpoint (host:port)."
  value = coalesce(
    try("${docker_container.postgres[0].name}:5432", null),
    try(aws_db_instance.aqp[0].endpoint, null),
    try(google_sql_database_instance.aqp[0].connection_name, null),
    try(azurerm_postgresql_flexible_server.aqp[0].fqdn, null),
  )
  sensitive = true
}

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

output "redis_url" {
  description = "Redis URL for the Celery broker + RAG layer."
  value = coalesce(
    try("rediss://${aws_elasticache_replication_group.aqp[0].primary_endpoint_address}:6379/0", null),
    try("redis://${google_redis_instance.aqp[0].host}:6379/0", null),
    try("rediss://${azurerm_redis_cache.aqp[0].hostname}:6380/0", null),
    "redis://localhost:6379/0",
  )
  sensitive = true
}

output "tags" {
  value = local.base_tags
}
