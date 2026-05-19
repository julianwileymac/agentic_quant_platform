variable "rpi_kubeconfig_path" {
  type        = string
  default     = "~/.kube/config"
  description = "Kubeconfig path for the rpi_kubernetes cluster."
}

variable "rpi_kube_context" {
  type        = string
  default     = ""
  description = "Optional kubeconfig context for rpi_kubernetes."
}

variable "rpi_namespace" {
  type    = string
  default = "aqp"
}

variable "app_version" {
  type    = string
  default = "latest"
}

variable "rpi_image_registry" {
  type        = string
  default     = "ghcr.io/julianwiley"
  description = "Registry reachable by rpi nodes. Images are expected as <registry>/aqp-<service>:<app_version>."
}

variable "rpi_ingress_host" {
  type    = string
  default = ""
}

variable "auth0_domain" {
  type    = string
  default = ""
}

variable "auth0_audience" {
  type    = string
  default = "https://aqp/api"
}

variable "auth0_client_id" {
  type    = string
  default = ""
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
    "aqp-api",
    "aqp-worker",
    "aqp-beat",
    "aqp-frontend",
    "postgres",
    "redis",
    "neo4j",
    "chromadb",
    "mlflow",
    "otel-collector",
    "jaeger",
  ]
  description = "Deployment topology service IDs enabled for the rpi target."
}

# ---------------------------------------------------------------------------
# Management Engine Phase D — optional Cloudflare Zero Trust edge.
# ---------------------------------------------------------------------------

variable "cloudflare_enabled" {
  type        = bool
  default     = false
  description = "When true, provision a Cloudflare tunnel + DNS routes + (optional) Access app."
}

variable "cloudflare_tunnel_name" {
  type        = string
  default     = "aqp-rpi-edge"
  description = "Tunnel name shown in the Cloudflare dashboard."
}

variable "cloudflare_account_id" {
  type        = string
  default     = ""
  description = "Cloudflare account id (required when cloudflare_enabled=true)."
  sensitive   = true
}

variable "cloudflare_zone_id" {
  type        = string
  default     = ""
  description = "Cloudflare DNS zone id (required when cloudflare_enabled=true)."
}

variable "cloudflare_ingress_rules" {
  type    = list(object({ hostname = string, service = string }))
  default = []
  description = <<-EOT
    List of ingress rules. Each item is { hostname, service }. The
    `service` typically points at the in-cluster ingress-nginx
    controller, e.g.
    'http://ingress-nginx-controller.ingress.svc.cluster.local:80'.
  EOT
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
  type    = any
  default = []
  description = "Cloudflare Access policies — see modules/cloudflare_edge/main.tf."
}
