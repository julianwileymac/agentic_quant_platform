variable "kubeconfig_path" {
  type        = string
  default     = "~/.kube/config"
  description = "Kubeconfig path for the tower+laptop cluster."
}

variable "kube_context" {
  type        = string
  default     = ""
  description = "Optional kubeconfig context."
}

variable "namespace" {
  type    = string
  default = "aqp"
}

variable "app_version" {
  type    = string
  default = "latest"
}

variable "image_registry" {
  type        = string
  default     = "docker.io/julian0215"
  description = "Registry reachable by cluster nodes."
}

variable "ingress_host" {
  type    = string
  default = "aqp.fund"
}

variable "auth0_domain" {
  type    = string
  default = "aqp-fund.us.auth0.com"
}

variable "auth0_audience" {
  type    = string
  default = "https://api.aqp.internal/manage"
}

variable "auth0_client_id" {
  type    = string
  default = "ZwJvVAYGRj6drndJhpKlvyLv18Jybavz"
}

variable "auth_scim_m2m_audience" {
  type        = string
  default     = ""
  description = "SCIM/M2M audience. Defaults to auth0_audience when empty."
}

variable "auth0_client_secret_secret_name" {
  type        = string
  default     = ""
  description = "Kubernetes Secret name holding the Auth0/OIDC client secret."
}

variable "auth_scim_bearer_token_hash_secret_name" {
  type        = string
  default     = ""
  description = "Kubernetes Secret name holding the SCIM bearer token hash."
}

variable "enabled_services" {
  type = list(string)
  default = [
    "aqp-core",
    "aqp-worker",
    "aqp-beat",
    "aqp-client",
    "aqp-cp",
    "postgres",
    "redis",
    "neo4j",
    "chromadb",
    "mlflow",
    "otel-collector",
    "jaeger",
    "questdb",
  ]
  description = "Deployment topology service IDs enabled for the tower target."
}

variable "cloudflare_enabled" {
  type        = bool
  default     = false
  description = "When true, provision Cloudflare tunnel + DNS routes + optional Access app."
}

variable "cloudflare_tunnel_name" {
  type        = string
  default     = "aqp-fund-edge"
  description = "Tunnel name shown in Cloudflare."
}

variable "cloudflare_account_id" {
  type        = string
  default     = ""
  description = "Cloudflare account id."
  sensitive   = true
}

variable "cloudflare_zone_id" {
  type        = string
  default     = ""
  description = "Cloudflare DNS zone id."
}

variable "cloudflare_ingress_rules" {
  type = list(object({ hostname = string, service = string }))
  default = [
    {
      hostname = "aqp.fund"
      service  = "http://aqp-client.aqp.svc.cluster.local:80"
    },
    {
      hostname = "api.aqp.fund"
      service  = "http://aqp-core.aqp.svc.cluster.local:8000"
    },
    {
      hostname = "manage.aqp.fund"
      service  = "http://aqp-cp.aqp-admin.svc.cluster.local:80"
    },
  ]
}

variable "cloudflare_enable_access_app" {
  type    = bool
  default = false
}

variable "cloudflare_access_app_name" {
  type    = string
  default = ""
}

variable "cloudflare_access_app_session_duration" {
  type    = string
  default = "24h"
}

variable "cloudflare_access_policies" {
  type        = any
  default     = []
  description = "Cloudflare Access policies."
}
