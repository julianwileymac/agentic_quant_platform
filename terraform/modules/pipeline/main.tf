###############################################################################
# pipeline — ingestion adapter Deployments + DuckDB worker StatefulSets.
###############################################################################

variable "cloud_provider" { type = string }
variable "environment"    { type = string }
variable "common_tags"    { type = map(string) default = {} }
variable "storage_outputs"    { type = any default = {} }
variable "kubernetes_outputs" { type = any default = {} }
variable "app_version"        { type = string default = "latest" }

locals {
  ns_system   = "aqp-system"
  ns_pipeline = "aqp-system"
}

# --- AQP API ----------------------------------------------------------------

resource "kubernetes_deployment" "api" {
  metadata {
    name      = "aqp-api"
    namespace = local.ns_system
    labels    = merge(var.common_tags, { app = "aqp-api" })
  }
  spec {
    replicas = var.environment == "live" ? 3 : 1
    selector { match_labels = { app = "aqp-api" } }
    strategy { type = "RollingUpdate" rolling_update { max_unavailable = "0" } }
    template {
      metadata { labels = merge(var.common_tags, { app = "aqp-api" }) }
      spec {
        service_account_name = "aqp-api"
        container {
          name  = "api"
          image = "aqp-api:${var.app_version}"
          port { container_port = 8000 }
          env_from {
            secret_ref { name = "aqp-postgres-password" }
          }
          env_from {
            secret_ref { name = "aqp-session-secret" }
          }
          env {
            name  = "AQP_REDIS_URL"
            value = try(var.storage_outputs.redis_url, "redis://redis.aqp-system.svc.cluster.local:6379")
          }
          resources {
            requests = { cpu = "500m" memory = "1Gi"   }
            limits   = { cpu = "2"    memory = "4Gi"   }
          }
          readiness_probe { http_get { path = "/health" port = 8000 } initial_delay_seconds = 10 }
          liveness_probe  { http_get { path = "/health" port = 8000 } initial_delay_seconds = 30 }
        }
      }
    }
  }
}

resource "kubernetes_service" "api" {
  metadata {
    name      = "aqp-api"
    namespace = local.ns_system
    labels    = var.common_tags
  }
  spec {
    selector = { app = "aqp-api" }
    port {
      port        = 8000
      target_port = 8000
    }
  }
}

# --- DuckDB analytics StatefulSet (NVMe scratch) ---------------------------

resource "kubernetes_stateful_set" "duckdb" {
  metadata {
    name      = "aqp-duckdb"
    namespace = local.ns_system
    labels    = merge(var.common_tags, { app = "aqp-duckdb" })
  }
  spec {
    service_name = "aqp-duckdb"
    replicas     = 1
    selector { match_labels = { app = "aqp-duckdb" } }
    template {
      metadata { labels = merge(var.common_tags, { app = "aqp-duckdb" }) }
      spec {
        service_account_name = "aqp-duckdb"
        container {
          name  = "duckdb"
          image = "aqp-api:${var.app_version}"
          command = ["python", "-m", "aqp.data.duckdb_worker"]
          resources {
            requests = { cpu = "1"    memory = "4Gi" }
            limits   = { cpu = "4"    memory = "16Gi" }
          }
          volume_mount {
            name       = "scratch"
            mount_path = "/scratch"
          }
        }
        affinity {
          node_affinity {
            preferred_during_scheduling_ignored_during_execution {
              weight = 100
              preference {
                match_expressions {
                  key      = "aqp.io/workload-class"
                  operator = "In"
                  values   = ["memory-optimized"]
                }
              }
            }
          }
        }
        volume {
          name = "scratch"
          empty_dir { medium = "Memory" size_limit = "8Gi" }
        }
      }
    }
  }
}

# --- Pipeline NetworkPolicy: egress to storage + iceberg + bigquery + redis -

resource "kubernetes_manifest" "pipeline_netpol" {
  manifest = {
    apiVersion = "networking.k8s.io/v1"
    kind       = "NetworkPolicy"
    metadata = {
      name      = "aqp-pipeline-egress"
      namespace = local.ns_pipeline
      labels    = var.common_tags
    }
    spec = {
      podSelector = { matchLabels = { app = "aqp-api" } }
      policyTypes = ["Egress"]
      egress = [
        # DNS
        {
          to    = [{ namespaceSelector = { matchLabels = { "kubernetes.io/metadata.name" = "kube-system" } } }]
          ports = [{ protocol = "UDP" port = 53 }, { protocol = "TCP" port = 53 }]
        },
        # Postgres + Redis + storage (cluster-internal)
        {
          to    = [{ namespaceSelector = { matchLabels = { "kubernetes.io/metadata.name" = "aqp-system" } } }]
          ports = [{ protocol = "TCP" port = 5432 }, { protocol = "TCP" port = 6379 }, { protocol = "TCP" port = 6432 }]
        },
      ]
    }
  }
}

output "api_service" {
  value = kubernetes_service.api.metadata[0].name
}
