###############################################################################
# modules/airflow — self-managed Airflow 2.10 on EKS.
#
# We DON'T use MWAA: AQP needs a custom plugin set (LineageWriter
# integration, paper-trading triggers) that MWAA does not allow.
# The community Helm chart drives the deployment; the Airflow
# webserver is fronted by the Linkerd mesh (rule 47 mTLS).
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    helm = { source = "hashicorp/helm", version = "~> 2.16" }
  }
}

variable "namespace" {
  type    = string
  default = "airflow"
}
variable "executor" {
  type    = string
  default = "KubernetesExecutor"
}
variable "fernet_key_secret_name" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}

resource "helm_release" "airflow" {
  name             = "airflow"
  repository       = "https://airflow.apache.org"
  chart            = "airflow"
  version          = "1.15.0"
  namespace        = var.namespace
  create_namespace = true

  set { name = "executor", value = var.executor }
  set { name = "webserverSecretKeySecretName", value = var.fernet_key_secret_name }
  set { name = "ingress.web.enabled", value = "true" }
  set { name = "ingress.web.ingressClassName", value = "alb" }
  set { name = "logs.persistence.enabled", value = "true" }
  set { name = "metrics.statsd.enabled", value = "true" }
  set { name = "config.core.load_examples", value = "false" }
}
