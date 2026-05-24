###############################################################################
# agents — trading bot pods with aqp-agent + aqp-data-mcp sidecar pair.
#
# Zero-egress NetworkPolicy isolates the aqp-agent container; the
# aqp-data-mcp sidecar holds the read-only Postgres / Redis / S3 surface
# the agent can use. The kill-switch secret is mounted as ``tmpfs``.
###############################################################################

variable "cloud_provider" { type = string }
variable "environment" { type = string }
variable "common_tags" {
  type    = map(string)
  default = {}
}
variable "namespaces" { type = map(string) }
variable "storage_outputs" {
  type    = any
  default = {}
}
variable "app_version" {
  type    = string
  default = "latest"
}
variable "bot_specs" {
  description = "List of bot specs to materialise as Deployments."
  type = list(object({
    name      = string
    config    = string
    image_tag = optional(string, "latest")
    dry_run   = optional(bool, true)
  }))
  default = []
}

locals {
  ns = var.namespaces["agents"]
}

# --- kill-switch secret (mounted as tmpfs) -----------------------------------

resource "kubernetes_secret" "kill_switch" {
  metadata {
    name      = "aqp-kill-switch"
    namespace = local.ns
    labels    = var.common_tags
  }
  type = "Opaque"
  data = {
    redis_url       = base64encode(try(var.storage_outputs.redis_url, "redis://redis.aqp-system.svc.cluster.local:6379"))
    kill_switch_key = base64encode("aqp:kill_switch")
  }
}

# --- ConfigMap per environment ----------------------------------------------

resource "kubernetes_config_map" "agent_runtime" {
  metadata {
    name      = "aqp-agent-runtime"
    namespace = local.ns
    labels    = var.common_tags
  }
  data = {
    "session.dry_run"  = tostring(var.environment != "live")
    "session.metrics"  = "true"
    "mcp.server.port"  = "8765"
    "parquet.lake.uri" = try(var.storage_outputs.object_store_url, "")
  }
}

# --- Per-bot Deployment (one pod = aqp-agent + aqp-data-mcp sidecar) -------

resource "kubernetes_deployment" "bot" {
  for_each = { for s in var.bot_specs : s.name => s }
  metadata {
    name      = "aqp-bot-${each.value.name}"
    namespace = local.ns
    labels    = merge(var.common_tags, { app = "aqp-bot", bot = each.value.name })
  }
  spec {
    replicas = 1
    selector { match_labels = { app = "aqp-bot", bot = each.value.name } }
    strategy {
      type = "RollingUpdate"
      rolling_update {
        max_unavailable = "0"
      }
    }
    template {
      metadata {
        labels = merge(var.common_tags, { app = "aqp-bot", bot = each.value.name })
      }
      spec {
        service_account_name = "aqp-bot"
        # --- agent container — zero external egress ---
        container {
          name    = "aqp-agent"
          image   = "aqp-agent:${each.value.image_tag}"
          command = ["python", "-m", "aqp.bots.run_bot", "--config", each.value.config]
          env {
            name  = "AQP_BOT_DRY_RUN"
            value = tostring(each.value.dry_run)
          }
          env {
            name  = "AQP_MCP_ENDPOINT"
            value = "http://localhost:8765"
          }
          resources {
            requests = {
              cpu    = "200m"
              memory = "512Mi"
            }
            limits = {
              cpu    = "1"
              memory = "2Gi"
            }
          }
          volume_mount {
            name       = "kill-switch-secret"
            mount_path = "/run/secrets/kill_switch"
            read_only  = true
          }
        }
        # --- aqp-data-mcp sidecar — holds the DB / Redis / S3 surface ---
        container {
          name    = "aqp-data-mcp"
          image   = "aqp-data-mcp:${each.value.image_tag}"
          command = ["aqp-data-mcp", "--host", "127.0.0.1", "--port", "8765"]
          env_from {
            config_map_ref { name = kubernetes_config_map.agent_runtime.metadata[0].name }
          }
          env_from {
            secret_ref { name = "aqp-postgres-password" }
          }
          resources {
            requests = {
              cpu    = "100m"
              memory = "256Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "1Gi"
            }
          }
        }
        volume {
          name = "kill-switch-secret"
          secret {
            secret_name = kubernetes_secret.kill_switch.metadata[0].name
          }
        }
      }
    }
  }
}

# --- NetworkPolicy — zero egress from aqp-agent container ----------------

resource "kubernetes_manifest" "agent_zero_egress" {
  manifest = {
    apiVersion = "networking.k8s.io/v1"
    kind       = "NetworkPolicy"
    metadata = {
      name      = "aqp-agent-zero-egress"
      namespace = local.ns
      labels    = var.common_tags
    }
    spec = {
      podSelector = { matchLabels = { app = "aqp-bot" } }
      policyTypes = ["Egress"]
      egress = [
        # Only DNS to the cluster's CoreDNS — every other connection
        # MUST come from the aqp-data-mcp sidecar via localhost.
        {
          to = [{ namespaceSelector = { matchLabels = { "kubernetes.io/metadata.name" = "kube-system" } } }]
          ports = [
            { protocol = "UDP", port = 53 },
            { protocol = "TCP", port = 53 },
          ]
        }
      ]
    }
  }
}

output "kill_switch_secret_name" {
  value = kubernetes_secret.kill_switch.metadata[0].name
}
