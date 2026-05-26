###############################################################################
# modules/observability-stack — kube-prometheus-stack + Loki + Tempo + ADOT.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    helm = { source = "hashicorp/helm", version = "~> 2.16" }
  }
}

variable "grafana_admin_password" {
  type      = string
  sensitive = true
}

resource "helm_release" "kube_prometheus_stack" {
  name             = "kube-prometheus-stack"
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "kube-prometheus-stack"
  version          = "65.1.1"
  namespace        = "aqp-observability"
  create_namespace = true

  set { name = "grafana.adminPassword", value = var.grafana_admin_password }
  set { name = "prometheus.prometheusSpec.retention", value = "15d" }
  set { name = "prometheus.prometheusSpec.thanos.objectStorageConfig.existingSecret.name", value = "thanos-objstore" }
  set { name = "prometheus.prometheusSpec.thanos.objectStorageConfig.existingSecret.key", value = "config.yaml" }
  set { name = "alertmanager.alertmanagerSpec.replicas", value = "3" }
}

resource "helm_release" "loki" {
  name             = "loki"
  repository       = "https://grafana.github.io/helm-charts"
  chart            = "loki-distributed"
  version          = "0.79.3"
  namespace        = "aqp-observability"
  create_namespace = true
  depends_on       = [helm_release.kube_prometheus_stack]
}

resource "helm_release" "tempo" {
  name             = "tempo"
  repository       = "https://grafana.github.io/helm-charts"
  chart            = "tempo-distributed"
  version          = "1.18.0"
  namespace        = "aqp-observability"
  create_namespace = true
  depends_on       = [helm_release.kube_prometheus_stack]
}

resource "helm_release" "adot" {
  name             = "adot"
  repository       = "https://aws-observability.github.io/aws-otel-helm-charts"
  chart            = "adot-exporter-for-eks-on-ec2"
  version          = "0.18.0"
  namespace        = "aqp-observability"
  create_namespace = true
  depends_on       = [helm_release.kube_prometheus_stack]
}
