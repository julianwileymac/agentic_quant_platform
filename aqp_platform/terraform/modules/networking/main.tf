variable "cloud_provider" { type = string }
variable "environment" { type = string }
variable "primary_domain" {
  type    = string
  default = ""
}
variable "nextjs_traffic_weight" {
  type    = number
  default = 100
  validation {
    condition     = var.nextjs_traffic_weight >= 0 && var.nextjs_traffic_weight <= 100
    error_message = "nextjs_traffic_weight must be between 0 and 100"
  }
}
variable "common_tags" {
  type    = map(string)
  default = {}
}

# Cloud-specific VPC / VNet shells (operators usually point at an
# existing VPC instead; these blocks are kept minimal to avoid
# over-prescribing network shape).
resource "aws_vpc" "aqp" {
  count                = var.cloud_provider == "aws" ? 1 : 0
  cidr_block           = "10.42.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = merge(var.common_tags, { Name = "aqp-${var.environment}" })
}

resource "google_compute_network" "aqp" {
  count                   = var.cloud_provider == "gcp" ? 1 : 0
  name                    = "aqp-${var.environment}"
  auto_create_subnetworks = false
}

resource "azurerm_virtual_network" "aqp" {
  count               = var.cloud_provider == "azure" ? 1 : 0
  name                = "aqp-${var.environment}"
  resource_group_name = ""
  location            = "eastus"
  address_space       = ["10.42.0.0/16"]
  tags                = var.common_tags
}

# Primary AQP Ingress — routes /api, /ws, /mcp/data, /, /legacy.
resource "kubernetes_ingress_v1" "aqp" {
  metadata {
    name      = "aqp-primary"
    namespace = "aqp-system"
    annotations = {
      "nginx.ingress.kubernetes.io/proxy-read-timeout" = "3600"
      "nginx.ingress.kubernetes.io/proxy-send-timeout" = "3600"
      "nginx.ingress.kubernetes.io/enable-cors"        = "true"
    }
  }
  spec {
    ingress_class_name = "nginx"
    dynamic "tls" {
      for_each = var.primary_domain != "" ? [1] : []
      content {
        hosts       = [var.primary_domain]
        secret_name = "aqp-primary-tls"
      }
    }
    rule {
      host = var.primary_domain
      http {
        path {
          path      = "/api"
          path_type = "Prefix"
          backend {
            service {
              name = "aqp-api"
              port { number = 8000 }
            }
          }
        }
        path {
          path      = "/ws"
          path_type = "Prefix"
          backend {
            service {
              name = "aqp-api"
              port { number = 8000 }
            }
          }
        }
        path {
          path      = "/"
          path_type = "Prefix"
          backend {
            service {
              name = "aqp-frontend"
              port { number = 3001 }
            }
          }
        }
      }
    }
  }
}

# Canary ingress — controls Solara (legacy) -> Next.js traffic split.
resource "kubernetes_ingress_v1" "aqp_canary" {
  metadata {
    name      = "aqp-frontend-canary"
    namespace = "aqp-system"
    annotations = {
      "nginx.ingress.kubernetes.io/canary"        = "true"
      "nginx.ingress.kubernetes.io/canary-weight" = tostring(var.nextjs_traffic_weight)
    }
  }
  spec {
    ingress_class_name = "nginx"
    rule {
      host = var.primary_domain
      http {
        path {
          path      = "/"
          path_type = "Prefix"
          backend {
            service {
              name = "aqp-frontend"
              port { number = 3001 }
            }
          }
        }
      }
    }
  }
}

# cert-manager ClusterIssuer — Let's Encrypt for cloud; self-signed for local.
resource "kubernetes_manifest" "cluster_issuer" {
  manifest = {
    apiVersion = "cert-manager.io/v1"
    kind       = "ClusterIssuer"
    metadata   = { name = "aqp-letsencrypt" }
    spec = var.cloud_provider == "local" ? {
      selfSigned = {}
      } : {
      acme = {
        server              = "https://acme-v02.api.letsencrypt.org/directory"
        email               = "admin@${var.primary_domain}"
        privateKeySecretRef = { name = "aqp-letsencrypt-key" }
        solvers             = [{ http01 = { ingress = { class = "nginx" } } }]
      }
    }
  }
}

# Default-deny NetworkPolicy on every aqp-* namespace.
resource "kubernetes_network_policy" "default_deny" {
  for_each = toset(["aqp-local", "aqp-paper", "aqp-live", "aqp-backtest", "aqp-system", "aqp-terraform"])
  metadata {
    name      = "default-deny"
    namespace = each.value
  }
  spec {
    pod_selector {}
    policy_types = ["Ingress", "Egress"]
  }
}

output "ingress_host" {
  value = var.primary_domain
}
