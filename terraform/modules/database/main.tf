###############################################################################
# database — PgBouncer connection pooler + Alembic migration Job.
###############################################################################

variable "cloud_provider" { type = string }
variable "environment"    { type = string }
variable "common_tags" {
  type    = map(string)
  default = {}
}
variable "storage_outputs" {
  type    = any
  default = {}
}
variable "kubernetes_outputs" {
  type    = any
  default = {}
}
variable "app_version" {
  type    = string
  default = "latest"
}

locals {
  namespace = "aqp-system"
  pgbouncer_image = "edoburu/pgbouncer:v1.23.1"
}

resource "kubernetes_config_map" "pgbouncer_ini" {
  metadata {
    name      = "aqp-pgbouncer-ini"
    namespace = local.namespace
    labels    = var.common_tags
  }
  data = {
    "pgbouncer.ini" = <<EOT
[databases]
aqp = host=${try(var.storage_outputs.postgres_endpoint, "postgres")} port=5432 dbname=aqp

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
reserve_pool_size = 5
server_idle_timeout = 600
EOT
    "userlist.txt" = "\"aqp\" \"md5_placeholder\"\n"
  }
}

resource "kubernetes_deployment" "pgbouncer" {
  metadata {
    name      = "aqp-pgbouncer"
    namespace = local.namespace
    labels    = merge(var.common_tags, { app = "aqp-pgbouncer" })
  }
  spec {
    replicas = 2
    selector { match_labels = { app = "aqp-pgbouncer" } }
    strategy {
      type = "RollingUpdate"
      rolling_update {
        max_unavailable = "0"
      }
    }
    template {
      metadata { labels = merge(var.common_tags, { app = "aqp-pgbouncer" }) }
      spec {
        service_account_name = "default"
        container {
          name  = "pgbouncer"
          image = local.pgbouncer_image
          port { container_port = 6432 }
          resources {
            requests = {
              cpu    = "100m"
              memory = "128Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "512Mi"
            }
          }
          readiness_probe {
            tcp_socket {
              port = 6432
            }
            initial_delay_seconds = 5
          }
          liveness_probe {
            tcp_socket {
              port = 6432
            }
            initial_delay_seconds = 15
          }
          volume_mount {
            name       = "config"
            mount_path = "/etc/pgbouncer"
          }
        }
        volume {
          name = "config"
          config_map { name = kubernetes_config_map.pgbouncer_ini.metadata[0].name }
        }
      }
    }
  }
}

resource "kubernetes_service" "pgbouncer" {
  metadata {
    name      = "aqp-pgbouncer"
    namespace = local.namespace
    labels    = var.common_tags
  }
  spec {
    selector = { app = "aqp-pgbouncer" }
    port {
      port        = 6432
      target_port = 6432
    }
  }
}

# --- Alembic migration Job ----------------------------------------------

resource "kubernetes_job" "alembic_migrate" {
  metadata {
    name      = "aqp-alembic-migrate-${replace(var.app_version, ".", "-")}"
    namespace = local.namespace
    labels    = var.common_tags
  }
  spec {
    backoff_limit              = 3
    ttl_seconds_after_finished = 86400
    template {
      metadata { labels = var.common_tags }
      spec {
        restart_policy = "Never"
        container {
          name    = "alembic"
          image   = "aqp-api:${var.app_version}"
          command = ["alembic", "upgrade", "head"]
          env_from {
            secret_ref { name = "aqp-postgres-password" }
          }
          env {
            name  = "AQP_POSTGRES_DSN"
            value = "postgresql+psycopg2://aqp:$(AQP_POSTGRES_PASSWORD)@aqp-pgbouncer.${local.namespace}.svc.cluster.local:6432/aqp"
          }
        }
      }
    }
  }
  wait_for_completion = false
  depends_on          = [kubernetes_deployment.pgbouncer]
}

# --- Prometheus exporter scrape -----------------------------------------

resource "kubernetes_manifest" "postgres_exporter_servicemonitor" {
  manifest = {
    apiVersion = "monitoring.coreos.com/v1"
    kind       = "ServiceMonitor"
    metadata = {
      name      = "aqp-postgres-exporter"
      namespace = local.namespace
      labels    = var.common_tags
    }
    spec = {
      selector = { matchLabels = { app = "aqp-postgres-exporter" } }
      endpoints = [{ port = "metrics", interval = "30s" }]
    }
  }
}

output "db_host" {
  value = "aqp-pgbouncer.${local.namespace}.svc.cluster.local"
}

output "db_port" {
  value = 6432
}
