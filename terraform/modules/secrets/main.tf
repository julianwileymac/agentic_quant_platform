variable "cloud_provider" { type = string }
variable "namespace"      { type = string }
variable "vault_backend" {
  description = "vault | aws_secretsmanager | gcp_secretmanager | azure_keyvault"
  type        = string
}
variable "vault_addr"          { type = string, default = "" }
variable "vault_mount"         { type = string, default = "secret" }
variable "aws_region"          { type = string, default = "us-east-1" }
variable "gcp_project_id"      { type = string, default = "" }
variable "gcp_region"          { type = string, default = "us-central1" }
variable "gcp_gke_cluster"     { type = string, default = "" }
variable "azure_tenant_id"     { type = string, default = "" }
variable "azure_keyvault_url"  { type = string, default = "" }
variable "common_tags" {
  type    = map(string)
  default = {}
}

variable "secret_mappings" {
  description = "Mapping of {k8s_secret_name = {vault_path, k8s_key}}."
  type = map(object({
    vault_path = string
    k8s_key    = string
  }))
  default = {
    "aqp-broker-api-key"      = { vault_path = "aqp/broker/api_key",      k8s_key = "AQP_BROKER_API_KEY" }
    "aqp-broker-api-secret"   = { vault_path = "aqp/broker/api_secret",   k8s_key = "AQP_BROKER_API_SECRET" }
    "aqp-db-password"         = { vault_path = "aqp/database/password",   k8s_key = "AQP_DB_PASSWORD" }
    "aqp-msal-client-secret"  = { vault_path = "aqp/msal/client_secret",  k8s_key = "AQP_MSAL_CLIENT_SECRET" }
    "aqp-redis-password"      = { vault_path = "aqp/redis/password",      k8s_key = "AQP_REDIS_PASSWORD" }
    "aqp-session-secret"      = { vault_path = "aqp/session/secret",      k8s_key = "AQP_AUTH_SESSION_SECRET" }
    "aqp-alpaca-secret"       = { vault_path = "aqp/alpaca/secret",       k8s_key = "AQP_ALPACA_SECRET_KEY" }
    "aqp-tradier-token"       = { vault_path = "aqp/tradier/token",       k8s_key = "AQP_TRADIER_TOKEN" }
    "aqp-alpha-vantage-key"   = { vault_path = "aqp/alpha_vantage/key",   k8s_key = "AQP_ALPHA_VANTAGE_API_KEY" }
    "aqp-fred-key"            = { vault_path = "aqp/fred/key",            k8s_key = "AQP_FRED_API_KEY" }
    "aqp-polaris-secret"      = { vault_path = "aqp/polaris/secret",      k8s_key = "AQP_POLARIS_CLIENT_SECRET" }
    "aqp-neo4j-password"      = { vault_path = "aqp/neo4j/password",      k8s_key = "AQP_NEO4J_PASSWORD" }
    "aqp-datahub-token"       = { vault_path = "aqp/datahub/token",       k8s_key = "AQP_DATAHUB_TOKEN" }
    "aqp-hcp-token"           = { vault_path = "aqp/hcp/token",           k8s_key = "AQP_HCP_TOKEN" }
    "aqp-mathpix-key"         = { vault_path = "aqp/mathpix/key",         k8s_key = "AQP_MATHPIX_APP_KEY" }
  }
}

# Local Vault Helm release (dev mode) — never run in production.
resource "helm_release" "vault_dev" {
  count            = var.cloud_provider == "local" && var.vault_backend == "vault" ? 1 : 0
  name             = "vault"
  repository       = "https://helm.releases.hashicorp.com"
  chart            = "vault"
  version          = "0.28.0"
  namespace        = "vault"
  create_namespace = true
  values = [yamlencode({
    server = { dev = { enabled = true, devRootToken = "aqp-dev-token" } }
    injector = { enabled = false }
  })]
}

# ClusterSecretStore — points at the configured backend.
resource "kubernetes_manifest" "cluster_secret_store" {
  manifest = {
    apiVersion = "external-secrets.io/v1beta1"
    kind       = "ClusterSecretStore"
    metadata   = { name = "aqp-secret-store" }
    spec = {
      provider = var.vault_backend == "vault" ? {
        vault = {
          server  = var.vault_addr != "" ? var.vault_addr : "http://vault.vault.svc.cluster.local:8200"
          path    = var.vault_mount
          version = "v2"
        }
      } : (var.vault_backend == "aws_secretsmanager" ? {
        aws = {
          service = "SecretsManager"
          region  = var.aws_region
          auth    = { jwt = { serviceAccountRef = { name = "external-secrets" } } }
        }
      } : (var.vault_backend == "gcp_secretmanager" ? {
        gcpsm = {
          projectID = var.gcp_project_id
          auth = {
            workloadIdentity = {
              clusterLocation   = var.gcp_region
              clusterName       = var.gcp_gke_cluster
              serviceAccountRef = { name = "external-secrets" }
            }
          }
        }
      } : {
        azurekv = {
          authType = "WorkloadIdentity"
          vaultUrl = var.azure_keyvault_url
          tenantId = var.azure_tenant_id
          serviceAccountRef = { name = "external-secrets", namespace = "external-secrets" }
        }
      }))
    }
  }
  depends_on = [helm_release.vault_dev]
}

# One ExternalSecret per (k8s_secret_name, vault_path).
resource "kubernetes_manifest" "external_secrets" {
  for_each = var.secret_mappings
  manifest = {
    apiVersion = "external-secrets.io/v1beta1"
    kind       = "ExternalSecret"
    metadata   = { name = each.key, namespace = var.namespace }
    spec = {
      refreshInterval = "1h"
      secretStoreRef  = { name = "aqp-secret-store", kind = "ClusterSecretStore" }
      target          = { name = each.key, creationPolicy = "Owner" }
      data = [{
        secretKey = each.value.k8s_key
        remoteRef = { key = each.value.vault_path }
      }]
    }
  }
  depends_on = [kubernetes_manifest.cluster_secret_store]
}

output "vault_backend" {
  value = var.vault_backend
}

output "synced_secrets" {
  value = sort(keys(var.secret_mappings))
}
