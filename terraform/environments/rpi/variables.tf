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
