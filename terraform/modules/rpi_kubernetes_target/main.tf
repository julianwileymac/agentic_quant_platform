terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
  }
}

locals {
  labels = merge(var.common_tags, {
    "app.kubernetes.io/managed-by" = "terraform"
    "app.kubernetes.io/part-of"    = "aqp"
    "aqp.io/target"                = "rpi_kubernetes"
  })
}

resource "kubernetes_namespace" "aqp" {
  metadata {
    name   = var.namespace
    labels = local.labels
  }
}

resource "kubernetes_config_map" "cluster_auth" {
  metadata {
    name      = "aqp-auth-config"
    namespace = kubernetes_namespace.aqp.metadata[0].name
    labels    = local.labels
  }

  data = {
    AQP_AUTH_PROVIDER          = "auth0"
    AQP_AUTH_REQUIRED          = "true"
    AQP_AUTH_ENFORCE           = "strict"
    AQP_AUTH_OIDC_ISSUER       = var.auth0_domain != "" ? "https://${var.auth0_domain}/" : ""
    AQP_AUTH_OIDC_AUDIENCE     = var.auth0_audience
    AQP_AUTH_OIDC_CLIENT_ID    = var.auth0_client_id
    AQP_AUTH_SCIM_ENABLED      = "true"
    AQP_AUTH_SCIM_M2M_AUDIENCE = var.auth_scim_m2m_audience != "" ? var.auth_scim_m2m_audience : var.auth0_audience
    AQP_KUBERNETES_ADAPTER     = "rpi_cluster"
    AQP_DEFAULT_CLOUD_PROVIDER = "rpi_cluster"
  }
}

resource "kubernetes_config_map" "frontend_auth" {
  metadata {
    name      = "aqp-frontend-auth-config"
    namespace = kubernetes_namespace.aqp.metadata[0].name
    labels    = local.labels
  }

  data = {
    VITE_AUTH_REQUIRED      = "true"
    VITE_AUTH0_DOMAIN       = var.auth0_domain
    VITE_AUTH0_AUDIENCE     = var.auth0_audience
    VITE_AUTH0_CLIENT_ID    = var.auth0_client_id
    VITE_AUTH0_REDIRECT_URI = var.ingress_host != "" ? "https://${var.ingress_host}/auth/callback" : ""
  }
}
