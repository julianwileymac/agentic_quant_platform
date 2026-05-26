###############################################################################
# modules/argocd-bootstrap — ArgoCD HA + app-of-apps seed.
#
# OIDC via AWS IAM Identity Center directly (no Dex). Helm release
# with HA controllers, repo servers, and applicationset replicas;
# the seed Application points at infrastructure/gitops/root/.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    helm       = { source = "hashicorp/helm",       version = "~> 2.16" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.32" }
  }
}

variable "argocd_domain" { type = string }
variable "oidc_issuer" { type = string }
variable "oidc_client_id" { type = string }
variable "rbac_csv" {
  description = "ArgoCD RBAC csv contents."
  type        = string
  default     = ""
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "helm_release" "argocd" {
  name             = "argocd"
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = "7.7.5"
  namespace        = "argocd"
  create_namespace = true

  values = [yamlencode({
    global = { domain = var.argocd_domain }
    configs = {
      params = { "server.insecure" = false }
      cm = {
        url            = "https://${var.argocd_domain}"
        "admin.enabled" = "false"
        "oidc.config" = yamlencode({
          name           = "AWS IAM Identity Center"
          issuer         = var.oidc_issuer
          clientID       = var.oidc_client_id
          clientSecret   = "$oidc.aws-sso.clientSecret"
          requestedScopes = ["openid", "profile", "email", "groups"]
        })
      }
      rbac = { "policy.csv" = var.rbac_csv }
    }
    controller     = { replicas = 2 }
    server         = { replicas = 3, autoscaling = { enabled = true, minReplicas = 3 } }
    repoServer     = { replicas = 3 }
    applicationSet = { replicas = 2 }
    "redis-ha"     = { enabled = true }
    dex            = { enabled = false }
    notifications  = { enabled = true }
  })]
}
