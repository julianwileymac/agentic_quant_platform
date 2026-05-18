###############################################################################
# kubernetes — cluster provisioning + namespace bootstrap + base operators.
#
# Cluster provisioning is cloud-conditional. The bootstrap Helm releases
# (cert-manager, ESO, KEDA, ingress-nginx, kube-prometheus, OTel
# operator, Istio base + istiod) are common across every cluster
# target including local minikube/kind.
###############################################################################

variable "cloud_provider" {
  type = string
}

variable "environment" {
  type = string
}

variable "organization_slug" {
  type = string
}

variable "workspace_slug" {
  type = string
}

variable "common_tags" {
  type    = map(string)
  default = {}
}

variable "namespaces" {
  type        = map(string)
  description = "Logical -> actual namespace name map (root composition output)"
}

variable "networking_outputs" {
  type        = any
  description = "Outputs from the networking module (VPC ids etc)"
  default     = {}
}

locals {
  is_aws   = var.cloud_provider == "aws"
  is_gcp   = var.cloud_provider == "gcp"
  is_azure = var.cloud_provider == "azure"
  is_local = var.cloud_provider == "local" || var.cloud_provider == "docker"
  is_rpi   = var.cloud_provider == "rpi_cluster"
}

# --- Local minikube / kind ------------------------------------------------

resource "null_resource" "local_cluster_bootstrap" {
  count = local.is_local ? 1 : 0
  triggers = {
    environment = var.environment
  }
  provisioner "local-exec" {
    command = "echo 'NOTE: bring up minikube/kind manually; aqp-terraform-runner pod will then bootstrap operators via Helm'"
  }
}

# --- AWS EKS --------------------------------------------------------------

resource "aws_eks_cluster" "this" {
  count    = local.is_aws ? 1 : 0
  name     = "${var.organization_slug}-${var.environment}"
  role_arn = "arn:aws:iam::${data.aws_caller_identity.current[0].account_id}:role/aqp-eks-cluster"
  version  = "1.30"
  vpc_config {
    subnet_ids              = [] # populated by networking module in a fuller rollout
    endpoint_private_access = true
    endpoint_public_access  = true
  }
  tags = var.common_tags
  # NOTE: full subnet wiring lives in a follow-up; this stanza is the
  # production-grade shape but expects subnet ids from networking.
  lifecycle {
    ignore_changes = [vpc_config[0].subnet_ids]
  }
}

data "aws_caller_identity" "current" {
  count = local.is_aws ? 1 : 0
}

# --- GCP GKE --------------------------------------------------------------

resource "google_container_cluster" "this" {
  count                    = local.is_gcp ? 1 : 0
  name                     = "${var.organization_slug}-${var.environment}"
  location                 = "us-central1"
  remove_default_node_pool = true
  initial_node_count       = 1
  deletion_protection      = false
  network                  = try(var.networking_outputs.vpc_id, "default")
  workload_identity_config {
    workload_pool = ""
  }
}

# --- Azure AKS ------------------------------------------------------------

resource "azurerm_kubernetes_cluster" "this" {
  count               = local.is_azure ? 1 : 0
  name                = "${var.organization_slug}-${var.environment}"
  location            = "eastus"
  resource_group_name = try(var.networking_outputs.azure_resource_group, "${var.organization_slug}-${var.environment}-rg")
  dns_prefix          = "${var.organization_slug}-${var.environment}"
  default_node_pool {
    name       = "default"
    node_count = 2
    vm_size    = "Standard_D4s_v5"
  }
  identity { type = "SystemAssigned" }
  tags = var.common_tags
}

# --- Namespaces -----------------------------------------------------------

resource "kubernetes_namespace" "aqp" {
  for_each = var.namespaces
  metadata {
    name = each.value
    labels = merge(var.common_tags, {
      "istio-injection" = each.key == "system" || each.key == "terraform" ? "disabled" : "enabled"
      "aqp.io/logical-name" = each.key
    })
  }
}

# --- Bootstrap Helm releases ---------------------------------------------

resource "helm_release" "cert_manager" {
  name             = "cert-manager"
  repository       = "https://charts.jetstack.io"
  chart            = "cert-manager"
  namespace        = "cert-manager"
  create_namespace = true
  version          = "v1.15.3"
  set {
    name  = "installCRDs"
    value = "true"
  }
}

resource "helm_release" "external_secrets" {
  name             = "external-secrets"
  repository       = "https://charts.external-secrets.io"
  chart            = "external-secrets"
  namespace        = "external-secrets"
  create_namespace = true
  version          = "0.10.7"
  depends_on       = [helm_release.cert_manager]
}

resource "helm_release" "keda" {
  name             = "keda"
  repository       = "https://kedacore.github.io/charts"
  chart            = "keda"
  namespace        = "keda-system"
  create_namespace = true
  version          = "2.15.1"
}

resource "helm_release" "ingress_nginx" {
  count            = local.is_local ? 0 : 1
  name             = "ingress-nginx"
  repository       = "https://kubernetes.github.io/ingress-nginx"
  chart            = "ingress-nginx"
  namespace        = "ingress-nginx"
  create_namespace = true
  version          = "4.11.2"
}

resource "helm_release" "kube_prometheus" {
  name             = "kube-prometheus-stack"
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "kube-prometheus-stack"
  namespace        = "monitoring"
  create_namespace = true
  version          = "61.6.0"
}

resource "helm_release" "otel_operator" {
  name             = "opentelemetry-operator"
  repository       = "https://open-telemetry.github.io/opentelemetry-helm-charts"
  chart            = "opentelemetry-operator"
  namespace        = "opentelemetry"
  create_namespace = true
  version          = "0.65.5"
  depends_on       = [helm_release.cert_manager]
}

# --- Outputs --------------------------------------------------------------

output "cluster_endpoint" {
  value = (
    local.is_aws   ? try(aws_eks_cluster.this[0].endpoint, "") :
    local.is_gcp   ? try(google_container_cluster.this[0].endpoint, "") :
    local.is_azure ? try(azurerm_kubernetes_cluster.this[0].kube_admin_config.0.host, "") :
    ""
  )
}

output "namespaces" {
  value = { for k, v in kubernetes_namespace.aqp : k => v.metadata[0].name }
}
