# Terraform runner — dedicated pod that runs `terraform plan/apply`.
#
# Mirrors the helm-runner pattern from rpi_kubernetes
# (kubernetes/bootstrap/helm-runner/) — dedicated namespace + RBAC,
# `restartPolicy: Never`, configmap-mounted values, two SA flavors
# (readonly for plan, writer for apply).

variable "namespace"          { type = string, default = "aqp-system" }
variable "runner_image"       { type = string, default = "aqp-terraform-runner:latest" }
variable "redis_address"      { type = string }
variable "kill_switch_key"    { type = string, default = "aqp:kill_switch" }
variable "common_tags" {
  type    = map(string)
  default = {}
}

resource "kubernetes_service_account" "readonly" {
  metadata {
    name      = "aqp-terraform-readonly"
    namespace = var.namespace
    labels    = merge(var.common_tags, { "app.kubernetes.io/component" = "terraform-runner-ro" })
  }
}

resource "kubernetes_service_account" "writer" {
  metadata {
    name      = "aqp-terraform-writer"
    namespace = var.namespace
    labels    = merge(var.common_tags, { "app.kubernetes.io/component" = "terraform-runner-rw" })
  }
}

resource "kubernetes_cluster_role" "runner_writer" {
  metadata { name = "aqp-terraform-writer" }
  rule {
    api_groups = ["*"]
    resources  = ["*"]
    verbs      = ["*"]
  }
}

resource "kubernetes_cluster_role_binding" "writer" {
  metadata { name = "aqp-terraform-writer" }
  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role.runner_writer.metadata[0].name
  }
  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.writer.metadata[0].name
    namespace = var.namespace
  }
}

resource "kubernetes_cluster_role" "runner_readonly" {
  metadata { name = "aqp-terraform-readonly" }
  rule {
    api_groups = ["*"]
    resources  = ["*"]
    verbs      = ["get", "list", "watch"]
  }
}

resource "kubernetes_cluster_role_binding" "readonly" {
  metadata { name = "aqp-terraform-readonly" }
  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role.runner_readonly.metadata[0].name
  }
  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.readonly.metadata[0].name
    namespace = var.namespace
  }
}

# Runner Deployment (single replica; Celery scales the queue, not pods).
resource "kubernetes_deployment" "runner" {
  metadata {
    name      = "aqp-terraform-runner"
    namespace = var.namespace
    labels    = merge(var.common_tags, { "app.kubernetes.io/name" = "aqp-terraform-runner" })
  }
  spec {
    replicas = 1
    strategy {
      type = "RollingUpdate"
      rolling_update {
        max_unavailable = "0"
        max_surge       = "1"
      }
    }
    selector { match_labels = { "app.kubernetes.io/name" = "aqp-terraform-runner" } }
    template {
      metadata { labels = { "app.kubernetes.io/name" = "aqp-terraform-runner" } }
      spec {
        service_account_name = kubernetes_service_account.writer.metadata[0].name
        # Kill-switch secret mounted as tmpfs (never persisted to disk).
        volume {
          name = "kill-switch"
          secret { secret_name = "aqp-kill-switch" }
        }
        volume {
          name = "workspace"
          empty_dir { medium = "Memory" }
        }
        container {
          name    = "runner"
          image   = var.runner_image
          command = ["celery", "-A", "aqp.tasks.celery_app", "worker", "-Q", "terraform", "--concurrency=1", "--loglevel=INFO"]
          env {
            name  = "AQP_REDIS_URL"
            value = var.redis_address
          }
          env {
            name  = "TF_IN_AUTOMATION"
            value = "1"
          }
          env {
            name  = "TF_INPUT"
            value = "0"
          }
          env {
            name  = "TF_PLUGIN_CACHE_DIR"
            value = "/tmp/aqp-tf-plugin-cache"
          }
          volume_mount {
            name       = "kill-switch"
            mount_path = "/run/secrets/kill_switch"
            read_only  = true
          }
          volume_mount {
            name       = "workspace"
            mount_path = "/tmp/aqp-terraform"
          }
          resources {
            requests = { cpu = "500m", memory = "1Gi" }
            limits   = { cpu = "4000m", memory = "8Gi" }
          }
          readiness_probe {
            exec { command = ["terraform", "version"] }
            initial_delay_seconds = 10
            period_seconds        = 30
          }
        }
      }
    }
  }
}

# NetworkPolicy: egress to the configured state backend + cloud APIs +
# the ESO sidecar service. Operators tighten this per environment.
resource "kubernetes_network_policy" "runner_egress" {
  metadata {
    name      = "aqp-terraform-runner-egress"
    namespace = var.namespace
  }
  spec {
    pod_selector {
      match_labels = { "app.kubernetes.io/name" = "aqp-terraform-runner" }
    }
    policy_types = ["Egress"]
    egress {
      to {
        namespace_selector {
          match_labels = { "kubernetes.io/metadata.name" = "external-secrets" }
        }
      }
    }
    # Default allow-all to cloud-provider control planes — operators
    # tighten via additional NetworkPolicy when needed.
    egress {
      to {
        ip_block {
          cidr   = "0.0.0.0/0"
          except = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
        }
      }
    }
  }
}

output "service_account_writer" {
  value = kubernetes_service_account.writer.metadata[0].name
}

output "service_account_readonly" {
  value = kubernetes_service_account.readonly.metadata[0].name
}
