###############################################################################
# aqp_workloads — Kubernetes Deployments / StatefulSets / Services /
# ConfigMaps / Secrets / Ingress for the AQP local stack.
#
# One-to-one mapping of every default service in docker-compose.yml:
#   redis (StatefulSet + headless Service)
#   postgres-pgvector (StatefulSet + headless Service)
#   neo4j (StatefulSet + headless Service)
#   chromadb (Deployment + Service)
#   mlflow (Deployment + Service)
#   otel-collector (Deployment + Service)
#   jaeger (Deployment + Service)
#   aqp-api (Deployment + Service + Ingress)
#   aqp-worker (Deployment)
#   aqp-beat (Deployment)
#   aqp-frontend (Deployment + Service + Ingress)
#
# Every resource gates on local/docker so cloud installs use the
# managed-services modules (database, storage, etc.).
###############################################################################

terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
  }
}

locals {
  is_local = contains(["local", "docker", "rpi_cluster"], var.cloud_provider)
  ns       = var.namespace

  common_labels = merge(var.common_tags, {
    "app.kubernetes.io/managed-by" = "terraform"
    "app.kubernetes.io/part-of"    = "aqp"
    "aqp.io/environment"           = var.environment
    "aqp.io/topology-target"       = var.deployment_topology_target
  })

  shared_env = [
    { name = "AQP_REDIS_URL", value = "redis://redis.${local.ns}.svc.cluster.local:6379/0" },
    { name = "AQP_REDIS_PUBSUB_URL", value = "redis://redis.${local.ns}.svc.cluster.local:6379/1" },
    { name = "AQP_POSTGRES_DSN", value = "postgresql+psycopg2://aqp:aqp@postgres.${local.ns}.svc.cluster.local:5432/aqp" },
    { name = "AQP_POSTGRES_ASYNC_DSN", value = "postgresql+asyncpg://aqp:aqp@postgres.${local.ns}.svc.cluster.local:5432/aqp" },
    { name = "AQP_NEO4J_URI", value = "bolt://neo4j.${local.ns}.svc.cluster.local:7687" },
    { name = "AQP_NEO4J_USER", value = "neo4j" },
    { name = "AQP_NEO4J_PASSWORD", value = "aqpneo4j" },
    { name = "AQP_NEO4J_DATABASE", value = "neo4j" },
    { name = "AQP_CHROMA_HOST", value = "chromadb.${local.ns}.svc.cluster.local" },
    { name = "AQP_CHROMA_PORT", value = "8000" },
    { name = "AQP_MLFLOW_TRACKING_URI", value = "http://mlflow.${local.ns}.svc.cluster.local:5000" },
    { name = "AQP_OLLAMA_HOST", value = var.ollama_host },
    { name = "AQP_OTEL_ENDPOINT", value = "http://otel-collector.${local.ns}.svc.cluster.local:4317" },
    { name = "AQP_ICEBERG_REST_URI", value = "" },
    { name = "AQP_ICEBERG_S3_WAREHOUSE", value = "" },
    { name = "AQP_ICEBERG_WAREHOUSE", value = "/warehouse/iceberg" },
    { name = "AQP_ICEBERG_STAGING_DIR", value = "/warehouse/staging" },
    { name = "AQP_ICEBERG_NAMESPACE_DEFAULT", value = "aqp" },
    { name = "AQP_TERRAFORM_ENABLED", value = "true" },
    { name = "AQP_ASSISTANT_ENGINE_ENABLED", value = "true" },
    { name = "AQP_ORCHESTRATION_STUDIO_ENABLED", value = "true" },
    { name = "HOME", value = "/app" },
    { name = "CREWAI_STORAGE_DIR", value = "/app/data/crewai" },
    { name = "XDG_DATA_HOME", value = "/app/data/xdg" },
  ]

  backend_secret_env = concat(
    var.auth0_client_secret_secret_name != "" ? [
      {
        name        = "AQP_AUTH_OIDC_CLIENT_SECRET"
        secret_name = var.auth0_client_secret_secret_name
        secret_key  = var.auth0_client_secret_secret_key
      }
    ] : [],
    var.auth_scim_bearer_token_hash_secret_name != "" ? [
      {
        name        = "AQP_AUTH_SCIM_BEARER_TOKEN_HASH"
        secret_name = var.auth_scim_bearer_token_hash_secret_name
        secret_key  = var.auth_scim_bearer_token_hash_secret_key
      }
    ] : [],
  )
}

# ---------------------------------------------------------------------------
# Datastores: redis / postgres / neo4j / chromadb
# ---------------------------------------------------------------------------

resource "kubernetes_stateful_set" "redis" {
  count = local.is_local && contains(var.enabled_services, "redis") ? 1 : 0
  metadata {
    name      = "redis"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "redis" })
  }
  spec {
    service_name = "redis"
    replicas     = 1
    selector {
      match_labels = { app = "redis" }
    }
    template {
      metadata {
        labels = merge(local.common_labels, { app = "redis" })
      }
      spec {
        container {
          name  = "redis"
          image = "redis:7-alpine"
          args  = ["redis-server", "--appendonly", "yes", "--notify-keyspace-events", "KEA"]
          port {
            container_port = 6379
            name           = "redis"
          }
          readiness_probe {
            tcp_socket { port = 6379 }
            initial_delay_seconds = 2
            period_seconds        = 5
          }
          volume_mount {
            name       = "redis-data"
            mount_path = "/data"
          }
        }
      }
    }
    volume_claim_template {
      metadata { name = "redis-data" }
      spec {
        access_modes = ["ReadWriteOnce"]
        resources { requests = { storage = "2Gi" } }
      }
    }
  }
}

resource "kubernetes_service" "redis" {
  count = local.is_local && contains(var.enabled_services, "redis") ? 1 : 0
  metadata {
    name      = "redis"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "redis" })
  }
  spec {
    cluster_ip = "None"
    selector   = { app = "redis" }
    port {
      name        = "redis"
      port        = 6379
      target_port = 6379
    }
  }
}

resource "kubernetes_stateful_set" "postgres" {
  count = local.is_local && contains(var.enabled_services, "postgres") ? 1 : 0
  metadata {
    name      = "postgres"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "postgres" })
  }
  spec {
    service_name = "postgres"
    replicas     = 1
    selector { match_labels = { app = "postgres" } }
    template {
      metadata { labels = merge(local.common_labels, { app = "postgres" }) }
      spec {
        container {
          name  = "postgres"
          image = "pgvector/pgvector:pg16"
          env {
            name  = "POSTGRES_USER"
            value = "aqp"
          }
          env {
            name  = "POSTGRES_PASSWORD"
            value = "aqp"
          }
          env {
            name  = "POSTGRES_DB"
            value = "aqp"
          }
          port {
            container_port = 5432
            name           = "pg"
          }
          readiness_probe {
            exec {
              command = ["pg_isready", "-U", "aqp", "-d", "aqp"]
            }
            initial_delay_seconds = 5
            period_seconds        = 5
          }
          volume_mount {
            name       = "pg-data"
            mount_path = "/var/lib/postgresql/data"
          }
        }
      }
    }
    volume_claim_template {
      metadata { name = "pg-data" }
      spec {
        access_modes = ["ReadWriteOnce"]
        resources { requests = { storage = "5Gi" } }
      }
    }
  }
}

resource "kubernetes_service" "postgres" {
  count = local.is_local && contains(var.enabled_services, "postgres") ? 1 : 0
  metadata {
    name      = "postgres"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "postgres" })
  }
  spec {
    cluster_ip = "None"
    selector   = { app = "postgres" }
    port {
      name        = "pg"
      port        = 5432
      target_port = 5432
    }
  }
}

resource "kubernetes_stateful_set" "neo4j" {
  count = local.is_local && contains(var.enabled_services, "neo4j") ? 1 : 0
  metadata {
    name      = "neo4j"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "neo4j" })
  }
  spec {
    service_name = "neo4j"
    replicas     = 1
    selector { match_labels = { app = "neo4j" } }
    template {
      metadata { labels = merge(local.common_labels, { app = "neo4j" }) }
      spec {
        container {
          name  = "neo4j"
          image = "neo4j:5-community"
          env {
            name  = "NEO4J_AUTH"
            value = "neo4j/aqpneo4j"
          }
          env {
            name  = "NEO4J_server_memory_heap_initial__size"
            value = "512m"
          }
          env {
            name  = "NEO4J_server_memory_heap_max__size"
            value = "1G"
          }
          env {
            name  = "NEO4J_dbms_security_procedures_unrestricted"
            value = "apoc.*"
          }
          port {
            name           = "http"
            container_port = 7474
          }
          port {
            name           = "bolt"
            container_port = 7687
          }
          readiness_probe {
            tcp_socket { port = 7687 }
            initial_delay_seconds = 10
            period_seconds        = 10
          }
          volume_mount {
            name       = "neo4j-data"
            mount_path = "/data"
          }
        }
      }
    }
    volume_claim_template {
      metadata { name = "neo4j-data" }
      spec {
        access_modes = ["ReadWriteOnce"]
        resources { requests = { storage = "2Gi" } }
      }
    }
  }
}

resource "kubernetes_service" "neo4j" {
  count = local.is_local && contains(var.enabled_services, "neo4j") ? 1 : 0
  metadata {
    name      = "neo4j"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "neo4j" })
  }
  spec {
    cluster_ip = "None"
    selector   = { app = "neo4j" }
    port {
      name        = "http"
      port        = 7474
      target_port = 7474
    }
    port {
      name        = "bolt"
      port        = 7687
      target_port = 7687
    }
  }
}

resource "kubernetes_deployment" "chromadb" {
  count = local.is_local && contains(var.enabled_services, "chromadb") ? 1 : 0
  metadata {
    name      = "chromadb"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "chromadb" })
  }
  spec {
    replicas = 1
    selector { match_labels = { app = "chromadb" } }
    template {
      metadata { labels = merge(local.common_labels, { app = "chromadb" }) }
      spec {
        container {
          name  = "chromadb"
          image = "chromadb/chroma:1.0.16"
          env {
            name  = "IS_PERSISTENT"
            value = "TRUE"
          }
          env {
            name  = "ANONYMIZED_TELEMETRY"
            value = "FALSE"
          }
          port {
            name           = "http"
            container_port = 8000
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "chromadb" {
  count = local.is_local && contains(var.enabled_services, "chromadb") ? 1 : 0
  metadata {
    name      = "chromadb"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "chromadb" })
  }
  spec {
    selector = { app = "chromadb" }
    port {
      name        = "http"
      port        = 8000
      target_port = 8000
    }
  }
}

# ---------------------------------------------------------------------------
# Observability: mlflow + jaeger + otel-collector (lightweight images,
# no Helm needed for the local target).
# ---------------------------------------------------------------------------

resource "kubernetes_deployment" "mlflow" {
  count = local.is_local && contains(var.enabled_services, "mlflow") ? 1 : 0
  metadata {
    name      = "mlflow"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "mlflow" })
  }
  spec {
    replicas = 1
    selector { match_labels = { app = "mlflow" } }
    template {
      metadata { labels = merge(local.common_labels, { app = "mlflow" }) }
      spec {
        container {
          name  = "mlflow"
          image = "ghcr.io/mlflow/mlflow:v2.11.1"
          command = [
            "bash", "-lc",
            "mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri sqlite:////mlflow/artifacts/mlflow.db --default-artifact-root /mlflow/artifacts",
          ]
          port {
            name           = "http"
            container_port = 5000
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "mlflow" {
  count = local.is_local && contains(var.enabled_services, "mlflow") ? 1 : 0
  metadata {
    name      = "mlflow"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "mlflow" })
  }
  spec {
    selector = { app = "mlflow" }
    port {
      name        = "http"
      port        = 5000
      target_port = 5000
    }
  }
}

resource "kubernetes_deployment" "jaeger" {
  count = local.is_local && contains(var.enabled_services, "jaeger") ? 1 : 0
  metadata {
    name      = "jaeger"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "jaeger" })
  }
  spec {
    replicas = 1
    selector { match_labels = { app = "jaeger" } }
    template {
      metadata { labels = merge(local.common_labels, { app = "jaeger" }) }
      spec {
        container {
          name  = "jaeger"
          image = "jaegertracing/all-in-one:1.62.0"
          env {
            name  = "COLLECTOR_OTLP_ENABLED"
            value = "true"
          }
          port {
            name           = "ui"
            container_port = 16686
          }
          port {
            name           = "otlp-grpc"
            container_port = 4317
          }
          port {
            name           = "otlp-http"
            container_port = 4318
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "jaeger" {
  count = local.is_local && contains(var.enabled_services, "jaeger") ? 1 : 0
  metadata {
    name      = "jaeger"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "jaeger" })
  }
  spec {
    selector = { app = "jaeger" }
    port {
      name        = "ui"
      port        = 16686
      target_port = 16686
    }
    port {
      name        = "otlp-grpc"
      port        = 14317
      target_port = 4317
    }
  }
}

resource "kubernetes_deployment" "otel_collector" {
  count = local.is_local && contains(var.enabled_services, "otel-collector") ? 1 : 0
  metadata {
    name      = "otel-collector"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "otel-collector" })
  }
  spec {
    replicas = 1
    selector { match_labels = { app = "otel-collector" } }
    template {
      metadata { labels = merge(local.common_labels, { app = "otel-collector" }) }
      spec {
        container {
          name  = "otel-collector"
          image = "otel/opentelemetry-collector-contrib:0.105.0"
          args  = ["--config=/etc/otelcol/config.yaml"]
          port {
            name           = "otlp-grpc"
            container_port = 4317
          }
          port {
            name           = "otlp-http"
            container_port = 4318
          }
          volume_mount {
            name       = "config"
            mount_path = "/etc/otelcol"
          }
        }
        volume {
          name = "config"
          config_map {
            name = kubernetes_config_map.otel_config[0].metadata[0].name
          }
        }
      }
    }
  }
}

resource "kubernetes_config_map" "otel_config" {
  count = local.is_local && contains(var.enabled_services, "otel-collector") ? 1 : 0
  metadata {
    name      = "otel-collector-config"
    namespace = local.ns
  }
  data = {
    "config.yaml" = <<-EOT
      receivers:
        otlp:
          protocols:
            grpc:
              endpoint: 0.0.0.0:4317
            http:
              endpoint: 0.0.0.0:4318
      exporters:
        debug:
          verbosity: basic
        otlp/jaeger:
          endpoint: jaeger.${local.ns}.svc.cluster.local:14317
          tls:
            insecure: true
      service:
        pipelines:
          traces:
            receivers: [otlp]
            exporters: [otlp/jaeger, debug]
          metrics:
            receivers: [otlp]
            exporters: [debug]
    EOT
  }
}

resource "kubernetes_service" "otel_collector" {
  count = local.is_local && contains(var.enabled_services, "otel-collector") ? 1 : 0
  metadata {
    name      = "otel-collector"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "otel-collector" })
  }
  spec {
    selector = { app = "otel-collector" }
    port {
      name        = "otlp-grpc"
      port        = 4317
      target_port = 4317
    }
    port {
      name        = "otlp-http"
      port        = 4318
      target_port = 4318
    }
  }
}

# ---------------------------------------------------------------------------
# AQP services: api / worker / beat / frontend
# ---------------------------------------------------------------------------

locals {
  api_image      = lookup(var.images, "api", "")
  worker_image   = lookup(var.images, "worker", "")
  beat_image     = lookup(var.images, "beat", lookup(var.images, "api", ""))
  frontend_image = lookup(var.images, "frontend", "")
}

resource "kubernetes_deployment" "aqp_api" {
  count = local.is_local && contains(var.enabled_services, "aqp-api") && local.api_image != "" ? 1 : 0
  metadata {
    name      = "aqp-api"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "aqp-api" })
    annotations = {
      "aqp.io/version"      = var.app_version
      "aqp.io/ready-marker" = var.ready_marker
    }
  }
  spec {
    replicas = 1
    selector { match_labels = { app = "aqp-api" } }
    template {
      metadata { labels = merge(local.common_labels, { app = "aqp-api" }) }
      spec {
        enable_service_links = false
        container {
          name              = "api"
          image             = local.api_image
          image_pull_policy = "Always"
          command           = ["uvicorn", "aqp.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
          dynamic "env_from" {
            for_each = var.auth_config_map_name != "" ? [var.auth_config_map_name] : []
            content {
              config_map_ref {
                name = env_from.value
              }
            }
          }
          dynamic "env" {
            for_each = local.shared_env
            content {
              name  = env.value.name
              value = env.value.value
            }
          }
          dynamic "env" {
            for_each = local.backend_secret_env
            content {
              name = env.value.name
              value_from {
                secret_key_ref {
                  name = env.value.secret_name
                  key  = env.value.secret_key
                }
              }
            }
          }
          port {
            name           = "http"
            container_port = 8000
          }
          readiness_probe {
            http_get {
              path = "/healthz"
              port = "http"
            }
            initial_delay_seconds = 10
            period_seconds        = 10
            failure_threshold     = 12
          }
          liveness_probe {
            http_get {
              path = "/healthz"
              port = "http"
            }
            initial_delay_seconds = 30
            period_seconds        = 30
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "aqp_api" {
  count = local.is_local && contains(var.enabled_services, "aqp-api") && local.api_image != "" ? 1 : 0
  metadata {
    name      = "aqp-api"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "aqp-api" })
  }
  spec {
    selector = { app = "aqp-api" }
    port {
      name        = "http"
      port        = 8000
      target_port = 8000
    }
  }
}

resource "kubernetes_deployment" "aqp_worker" {
  count = local.is_local && contains(var.enabled_services, "aqp-worker") && local.worker_image != "" ? 1 : 0
  metadata {
    name      = "aqp-worker"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "aqp-worker" })
    annotations = {
      "aqp.io/version"      = var.app_version
      "aqp.io/ready-marker" = var.ready_marker
    }
  }
  spec {
    replicas = 1
    selector { match_labels = { app = "aqp-worker" } }
    template {
      metadata { labels = merge(local.common_labels, { app = "aqp-worker" }) }
      spec {
        enable_service_links = false
        container {
          name              = "worker"
          image             = local.worker_image
          image_pull_policy = "Always"
          command = [
            "celery", "-A", "aqp.tasks.celery_app", "worker",
            "--loglevel=info",
            "-Q", "default,backtest,agents,ingestion,paper,hft,terraform",
            "--concurrency=2",
          ]
          dynamic "env_from" {
            for_each = var.auth_config_map_name != "" ? [var.auth_config_map_name] : []
            content {
              config_map_ref {
                name = env_from.value
              }
            }
          }
          dynamic "env" {
            for_each = local.shared_env
            content {
              name  = env.value.name
              value = env.value.value
            }
          }
          dynamic "env" {
            for_each = local.backend_secret_env
            content {
              name = env.value.name
              value_from {
                secret_key_ref {
                  name = env.value.secret_name
                  key  = env.value.secret_key
                }
              }
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_deployment" "aqp_beat" {
  count = local.is_local && contains(var.enabled_services, "aqp-beat") && local.beat_image != "" ? 1 : 0
  metadata {
    name      = "aqp-beat"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "aqp-beat" })
    annotations = {
      "aqp.io/version"      = var.app_version
      "aqp.io/ready-marker" = var.ready_marker
    }
  }
  spec {
    replicas = 1
    selector { match_labels = { app = "aqp-beat" } }
    template {
      metadata { labels = merge(local.common_labels, { app = "aqp-beat" }) }
      spec {
        enable_service_links = false
        container {
          name              = "beat"
          image             = local.beat_image
          image_pull_policy = "Always"
          command           = ["celery", "-A", "aqp.tasks.celery_app", "beat", "--loglevel=info"]
          dynamic "env_from" {
            for_each = var.auth_config_map_name != "" ? [var.auth_config_map_name] : []
            content {
              config_map_ref {
                name = env_from.value
              }
            }
          }
          dynamic "env" {
            for_each = local.shared_env
            content {
              name  = env.value.name
              value = env.value.value
            }
          }
          dynamic "env" {
            for_each = local.backend_secret_env
            content {
              name = env.value.name
              value_from {
                secret_key_ref {
                  name = env.value.secret_name
                  key  = env.value.secret_key
                }
              }
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_deployment" "aqp_frontend" {
  count = local.is_local && contains(var.enabled_services, "aqp-frontend") && local.frontend_image != "" ? 1 : 0
  metadata {
    name      = "aqp-frontend"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "aqp-frontend" })
    annotations = {
      "aqp.io/version"      = var.app_version
      "aqp.io/ready-marker" = var.ready_marker
    }
  }
  spec {
    replicas = 1
    selector { match_labels = { app = "aqp-frontend" } }
    template {
      metadata { labels = merge(local.common_labels, { app = "aqp-frontend" }) }
      spec {
        enable_service_links = false
        container {
          name              = "frontend"
          image             = local.frontend_image
          image_pull_policy = "Always"
          dynamic "env_from" {
            for_each = var.frontend_auth_config_map_name != "" ? [var.frontend_auth_config_map_name] : []
            content {
              config_map_ref {
                name = env_from.value
              }
            }
          }
          port {
            name           = "http"
            container_port = 80
          }
          readiness_probe {
            http_get {
              path = "/"
              port = "http"
            }
            initial_delay_seconds = 5
            period_seconds        = 5
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "aqp_frontend" {
  count = local.is_local && contains(var.enabled_services, "aqp-frontend") && local.frontend_image != "" ? 1 : 0
  metadata {
    name      = "aqp-frontend"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "aqp-frontend" })
  }
  spec {
    selector = { app = "aqp-frontend" }
    port {
      name        = "http"
      port        = 80
      target_port = 80
    }
  }
}

# ---------------------------------------------------------------------------
# Ingress — Traefik on k3d. Routes:
#   /           -> aqp-frontend:80
#   /api/       -> aqp-api:8000  (rewritten to / before forwarding)
# ---------------------------------------------------------------------------

resource "kubernetes_ingress_v1" "aqp" {
  count = local.is_local && contains(var.enabled_services, "aqp-api") && contains(var.enabled_services, "aqp-frontend") && local.api_image != "" && local.frontend_image != "" ? 1 : 0
  metadata {
    name      = "aqp"
    namespace = local.ns
    labels    = merge(local.common_labels, { app = "aqp" })
    annotations = {
      "ingress.kubernetes.io/ssl-redirect"               = "false"
      "traefik.ingress.kubernetes.io/router.entrypoints" = "web"
    }
  }
  spec {
    ingress_class_name = var.ingress_class
    rule {
      http {
        path {
          path      = "/"
          path_type = "Prefix"
          backend {
            service {
              name = kubernetes_service.aqp_frontend[0].metadata[0].name
              port { number = 80 }
            }
          }
        }
        path {
          path      = "/api"
          path_type = "Prefix"
          backend {
            service {
              name = kubernetes_service.aqp_api[0].metadata[0].name
              port { number = 8000 }
            }
          }
        }
      }
    }
  }
}
