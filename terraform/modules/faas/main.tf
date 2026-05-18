###############################################################################
# faas — KEDA ScaledObjects per Celery queue + matching worker Deployments.
#
# KEDA itself ships as a Helm release from the kubernetes module. This
# module only declares the ScaledObject + worker Deployment pairs.
###############################################################################

variable "cloud_provider" {
  type = string
}
variable "environment" {
  type = string
}
variable "common_tags" {
  type    = map(string)
  default = {}
}
variable "namespaces" {
  type = map(string)
}
variable "storage_outputs" {
  type    = any
  default = {}
}
variable "app_version" {
  type    = string
  default = "latest"
}

locals {
  ns = var.namespaces["live"] # workers run in the env's primary ns
  queue_config = {
    "default" = {
      min         = 1
      max         = 20
      list_length = 5
      resources = {
        cpu    = "200m"
        memory = "256Mi"
      }
    }
    "backtest" = {
      min         = 0
      max         = 100
      list_length = 1
      resources = {
        cpu    = "1"
        memory = "4Gi"
      }
    }
    "agents" = {
      min         = 0
      max         = 20
      list_length = 1
      resources = {
        cpu    = "500m"
        memory = "1Gi"
      }
    }
    "ml" = {
      min         = 0
      max         = 50
      list_length = 1
      resources = {
        cpu    = "2"
        memory = "8Gi"
      }
    }
    "ingestion" = {
      min         = 0
      max         = 30
      list_length = 5
      resources = {
        cpu    = "500m"
        memory = "1Gi"
      }
    }
    "training" = {
      min         = 0
      max         = 20
      list_length = 1
      resources = {
        cpu    = "4"
        memory = "16Gi"
      }
    }
    "paper" = {
      min         = 0
      max         = 10
      list_length = 1
      resources = {
        cpu    = "500m"
        memory = "1Gi"
      }
    }
    "rag" = {
      min         = 0
      max         = 10
      list_length = 1
      resources = {
        cpu    = "1"
        memory = "2Gi"
      }
    }
    "factors" = {
      min         = 0
      max         = 20
      list_length = 1
      resources = {
        cpu    = "1"
        memory = "2Gi"
      }
    }
    "hft" = {
      min         = 0
      max         = 5
      list_length = 1
      resources = {
        cpu    = "2"
        memory = "4Gi"
      }
    }
    "terraform" = {
      min         = 0
      max         = 10
      list_length = 1
      resources = {
        cpu    = "500m"
        memory = "1Gi"
      }
    }
  }
  redis_address = try(replace(replace(var.storage_outputs.redis_url, "redis://", ""), "rediss://", ""), "redis.aqp-system.svc.cluster.local:6379")
}

# Per-queue worker Deployment. ``aqp-celery-<queue>-worker`` is the
# canonical deployment name; the matching ScaledObject below targets it.
resource "kubernetes_deployment" "worker" {
  for_each = local.queue_config
  metadata {
    name      = "aqp-celery-${each.key}-worker"
    namespace = local.ns
    labels    = merge(var.common_tags, { app = "aqp-worker", queue = each.key })
  }
  spec {
    replicas = each.value.min
    selector { match_labels = { app = "aqp-worker", queue = each.key } }
    strategy {
      type = "RollingUpdate"
      rolling_update {
        max_unavailable = "0"
      }
    }
    template {
      metadata { labels = merge(var.common_tags, { app = "aqp-worker", queue = each.key }) }
      spec {
        service_account_name = "aqp-worker"
        container {
          name    = "worker"
          image   = "aqp-worker:${var.app_version}"
          command = ["celery", "-A", "aqp.tasks.celery_app", "worker", "-Q", each.key, "-l", "INFO"]
          resources {
            requests = each.value.resources
            limits   = each.value.resources
          }
          readiness_probe {
            exec {
              command = ["python", "-c", "from aqp.tasks.celery_app import celery_app; celery_app.control.ping(timeout=5)"]
            }
            initial_delay_seconds = 30
          }
          liveness_probe {
            exec {
              command = ["python", "-c", "from aqp.tasks.celery_app import celery_app; celery_app.control.ping(timeout=5)"]
            }
            initial_delay_seconds = 60
          }
        }
        # PodDisruptionBudget-style affinity: ML + backtest -> memory-opt;
        # agents/default -> burstable; terraform -> dedicated.
        affinity {
          node_affinity {
            preferred_during_scheduling_ignored_during_execution {
              weight = 100
              preference {
                match_expressions {
                  key      = "aqp.io/workload-class"
                  operator = "In"
                  values   = [each.key == "ml" || each.key == "backtest" ? "memory-optimized" : "burstable"]
                }
              }
            }
          }
        }
      }
    }
  }
}

# Pod disruption budget for the agent worker — prevents drain during
# active trading sessions.
resource "kubernetes_manifest" "agent_pdb" {
  manifest = {
    apiVersion = "policy/v1"
    kind       = "PodDisruptionBudget"
    metadata = {
      name      = "aqp-celery-agents-pdb"
      namespace = local.ns
      labels    = var.common_tags
    }
    spec = {
      minAvailable = 1
      selector     = { matchLabels = { app = "aqp-worker", queue = "agents" } }
    }
  }
}

# KEDA ScaledObject — one per queue.
resource "kubernetes_manifest" "scaled_object" {
  for_each = local.queue_config
  manifest = {
    apiVersion = "keda.sh/v1alpha1"
    kind       = "ScaledObject"
    metadata = {
      name      = "aqp-celery-${each.key}-scaler"
      namespace = local.ns
      labels    = var.common_tags
    }
    spec = {
      scaleTargetRef = {
        name = "aqp-celery-${each.key}-worker"
      }
      minReplicaCount = each.value.min
      maxReplicaCount = each.value.max
      pollingInterval = 30
      cooldownPeriod  = 300
      triggers = [{
        type = "redis"
        metadata = {
          address       = local.redis_address
          listName      = each.key
          listLength    = tostring(each.value.list_length)
          databaseIndex = "0"
        }
      }]
    }
  }
}

output "scaled_objects" {
  value = [for q in keys(local.queue_config) : "aqp-celery-${q}-scaler"]
}
