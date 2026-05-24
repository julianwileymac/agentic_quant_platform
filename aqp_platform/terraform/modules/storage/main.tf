###############################################################################
# storage — Postgres + Redis + object store + Iceberg catalog (per cloud).
#
# Inputs live in variables.tf; this file declares only the locals + resources.
###############################################################################

variable "networking_outputs" {
  type    = any
  default = {}
}

variable "kubernetes_outputs" {
  type    = any
  default = {}
}

locals {
  is_aws   = var.cloud_provider == "aws"
  is_gcp   = var.cloud_provider == "gcp"
  is_azure = var.cloud_provider == "azure"
  is_local = var.cloud_provider == "local" || var.cloud_provider == "docker"
}

# --- AWS: RDS + S3 + ElastiCache -----------------------------------------

resource "aws_db_instance" "pg" {
  count                       = local.is_aws ? 1 : 0
  identifier                  = "${var.organization_slug}-${var.environment}-pg"
  engine                      = "postgres"
  engine_version              = "16.3"
  instance_class              = "db.t4g.medium"
  allocated_storage           = 50
  storage_encrypted           = true
  multi_az                    = var.environment == "live"
  publicly_accessible         = false
  backup_retention_period     = 7
  deletion_protection         = var.environment == "live"
  db_name                     = "aqp"
  username                    = "aqp"
  manage_master_user_password = true
  parameter_group_name        = aws_db_parameter_group.pg[0].name
  tags                        = var.common_tags
}

resource "aws_db_parameter_group" "pg" {
  count  = local.is_aws ? 1 : 0
  family = "postgres16"
  name   = "${var.organization_slug}-${var.environment}-pg"
  parameter {
    name         = "shared_preload_libraries"
    value        = "pg_stat_statements"
    apply_method = "pending-reboot"
  }
  parameter {
    name  = "pg_stat_statements.track"
    value = "all"
  }
  parameter {
    name         = "max_connections"
    value        = "200"
    apply_method = "pending-reboot"
  }
  tags = var.common_tags
}

resource "aws_s3_bucket" "lake" {
  count  = local.is_aws ? 1 : 0
  bucket = "${var.organization_slug}-${var.environment}-aqp-lake"
  tags   = var.common_tags
}

resource "aws_s3_bucket_versioning" "lake" {
  count  = local.is_aws ? 1 : 0
  bucket = aws_s3_bucket.lake[0].id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  count  = local.is_aws ? 1 : 0
  bucket = aws_s3_bucket.lake[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "lake" {
  count                   = local.is_aws ? 1 : 0
  bucket                  = aws_s3_bucket.lake[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "lake" {
  count  = local.is_aws ? 1 : 0
  bucket = aws_s3_bucket.lake[0].id
  rule {
    id     = "archive-old"
    status = "Enabled"
    filter {}
    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }
  }
}

resource "aws_elasticache_replication_group" "redis" {
  count                      = local.is_aws ? 1 : 0
  replication_group_id       = "${var.organization_slug}-${var.environment}-redis"
  description                = "AQP Redis broker + RAG"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = var.environment == "live" ? "cache.r6g.large" : "cache.t4g.small"
  parameter_group_name       = "default.redis7"
  num_cache_clusters         = var.environment == "live" ? 2 : 1
  automatic_failover_enabled = var.environment == "live"
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  tags                       = var.common_tags
}

# --- GCP: Cloud SQL + GCS + Memorystore -----------------------------------

resource "google_sql_database_instance" "pg" {
  count            = local.is_gcp ? 1 : 0
  name             = "${var.organization_slug}-${var.environment}-pg"
  database_version = "POSTGRES_16"
  region           = "us-central1"
  settings {
    tier              = var.environment == "live" ? "db-custom-2-7680" : "db-f1-micro"
    availability_type = var.environment == "live" ? "REGIONAL" : "ZONAL"
    backup_configuration { enabled = true }
    database_flags {
      name  = "shared_preload_libraries"
      value = "pg_stat_statements"
    }
    database_flags {
      name  = "max_connections"
      value = "200"
    }
  }
  deletion_protection = var.environment == "live"
}

resource "google_storage_bucket" "lake" {
  count                       = local.is_gcp ? 1 : 0
  name                        = "${var.organization_slug}-${var.environment}-aqp-lake"
  location                    = "US"
  uniform_bucket_level_access = true
  versioning { enabled = true }
  lifecycle_rule {
    condition { age = 90 }
    action {
      type          = "SetStorageClass"
      storage_class = "ARCHIVE"
    }
  }
  labels = var.common_tags
}

resource "google_redis_instance" "redis" {
  count          = local.is_gcp ? 1 : 0
  name           = "${var.organization_slug}-${var.environment}-redis"
  tier           = var.environment == "live" ? "STANDARD_HA" : "BASIC"
  memory_size_gb = 1
  region         = "us-central1"
  redis_version  = "REDIS_7_0"
}

# --- Azure: Postgres Flex + ADLS + Azure Cache for Redis -----------------

resource "azurerm_postgresql_flexible_server" "pg" {
  count                  = local.is_azure ? 1 : 0
  name                   = "${var.organization_slug}-${var.environment}-pg"
  resource_group_name    = try(var.networking_outputs.azure_resource_group, "aqp-${var.environment}-rg")
  location               = "eastus"
  version                = "16"
  administrator_login    = "aqp"
  administrator_password = "P@ssw0rd-rotate-via-keyvault"
  storage_mb             = 32768
  sku_name               = var.environment == "live" ? "GP_Standard_D4s_v3" : "B_Standard_B1ms"
  zone                   = "1"
  tags                   = var.common_tags
}

resource "azurerm_storage_account" "lake" {
  count                    = local.is_azure ? 1 : 0
  name                     = replace("${var.organization_slug}${var.environment}lake", "-", "")
  resource_group_name      = try(var.networking_outputs.azure_resource_group, "aqp-${var.environment}-rg")
  location                 = "eastus"
  account_tier             = "Standard"
  account_replication_type = var.environment == "live" ? "ZRS" : "LRS"
  account_kind             = "StorageV2"
  is_hns_enabled           = true
  tags                     = var.common_tags
}

resource "azurerm_redis_cache" "redis" {
  count                = local.is_azure ? 1 : 0
  name                 = "${var.organization_slug}-${var.environment}-redis"
  resource_group_name  = try(var.networking_outputs.azure_resource_group, "aqp-${var.environment}-rg")
  location             = "eastus"
  capacity             = 1
  family               = "C"
  sku_name             = var.environment == "live" ? "Standard" : "Basic"
  non_ssl_port_enabled = false
  minimum_tls_version  = "1.2"
  tags                 = var.common_tags
}

# --- Local: Docker containers --------------------------------------------

resource "docker_container" "local_pg" {
  count = local.is_local ? 1 : 0
  name  = "aqp-${var.environment}-pg"
  image = "postgres:16-alpine"
  ports {
    internal = 5432
    external = 5432
  }
  env = [
    "POSTGRES_USER=aqp",
    "POSTGRES_DB=aqp",
    "POSTGRES_PASSWORD=aqp",
  ]
  restart = "unless-stopped"
}

resource "docker_container" "local_redis" {
  count = local.is_local ? 1 : 0
  name  = "aqp-${var.environment}-redis"
  image = "redis/redis-stack:7.4.0-v0"
  ports {
    internal = 6379
    external = 6379
  }
  command = ["redis-server", "--appendonly", "yes", "--maxmemory-policy", "allkeys-lru"]
  restart = "unless-stopped"
}

resource "docker_container" "local_minio" {
  count = local.is_local ? 1 : 0
  name  = "aqp-${var.environment}-minio"
  image = "minio/minio:latest"
  ports {
    internal = 9000
    external = 9000
  }
  ports {
    internal = 9001
    external = 9001
  }
  env = [
    "MINIO_ROOT_USER=aqp",
    "MINIO_ROOT_PASSWORD=aqp-minio-secret",
  ]
  command = ["server", "/data", "--console-address", ":9001"]
  restart = "unless-stopped"
}

# --- Outputs --------------------------------------------------------------

output "postgres_endpoint" {
  value = (
    local.is_aws ? try(aws_db_instance.pg[0].endpoint, "") :
    local.is_gcp ? try(google_sql_database_instance.pg[0].private_ip_address, "") :
    local.is_azure ? try(azurerm_postgresql_flexible_server.pg[0].fqdn, "") :
    local.is_local ? "localhost:5432" :
    ""
  )
}

output "object_store_url" {
  value = (
    local.is_aws ? try("s3://${aws_s3_bucket.lake[0].bucket}", "") :
    local.is_gcp ? try("gs://${google_storage_bucket.lake[0].name}", "") :
    local.is_azure ? try(azurerm_storage_account.lake[0].primary_dfs_endpoint, "") :
    local.is_local ? "http://localhost:9000" :
    ""
  )
}

output "redis_url" {
  value = (
    local.is_aws ? try("redis://${aws_elasticache_replication_group.redis[0].primary_endpoint_address}:6379", "") :
    local.is_gcp ? try("redis://${google_redis_instance.redis[0].host}:${google_redis_instance.redis[0].port}", "") :
    local.is_azure ? try("rediss://${azurerm_redis_cache.redis[0].hostname}:6380", "") :
    local.is_local ? "redis://localhost:6379" :
    ""
  )
}
