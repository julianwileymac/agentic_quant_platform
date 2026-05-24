###############################################################################
# aqp_workloads — inputs.
###############################################################################

variable "cloud_provider" {
  type        = string
  description = "Active cloud provider. Workloads only deploy when local/docker (other clouds use cloud-managed Postgres/Redis)."
}

variable "environment" {
  type        = string
  description = "Environment slug (typically 'local')."
}

variable "namespace" {
  type        = string
  description = "Kubernetes namespace AQP services land in. Created by the kubernetes module ahead of this one."
}

variable "namespaces" {
  type        = map(string)
  default     = {}
  description = "Optional logical -> actual namespace map (forwarded from the root composition)."
}

variable "images" {
  type        = map(string)
  description = "Service -> image reference map produced by module.aqp_images."
}

variable "app_version" {
  type    = string
  default = "latest"
}

variable "ingress_class" {
  type        = string
  default     = "traefik"
  description = "k3d ships Traefik out of the box; cloud installs override this with their own ingress class."
}

variable "warehouse_host_path" {
  type        = string
  default     = "/var/lib/aqp-warehouse"
  description = "Host path mounted into the api/worker pods for the Iceberg warehouse. Defaults to /var/lib/aqp-warehouse so the cluster can persist across restarts."
}

variable "ollama_host" {
  type        = string
  default     = "http://host.docker.internal:11434"
  description = "Ollama endpoint reachable from inside the cluster. k3d injects host.docker.internal -> host gateway automatically."
}

variable "common_tags" {
  type    = map(string)
  default = {}
}

variable "ready_marker" {
  type        = string
  default     = ""
  description = "Pseudo-input wired to module.aqp_images.ready so workloads only deploy after images are pushed."
}

variable "deployment_topology_target" {
  type        = string
  default     = ""
  description = "Deployment topology target id (for labels and drift checks)."
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
  ]
  description = "Deployment topology service IDs enabled for this target."
}

variable "auth_config_map_name" {
  type        = string
  default     = ""
  description = "Optional ConfigMap containing public backend auth/SCIM runtime settings."
}

variable "frontend_auth_config_map_name" {
  type        = string
  default     = ""
  description = "Optional ConfigMap containing public frontend auth settings."
}

variable "control_plane_auth_config_map_name" {
  type        = string
  default     = ""
  description = "Optional ConfigMap containing public/runtime auth settings for aqp_control_plane."
}

variable "auth0_client_secret_secret_name" {
  type        = string
  default     = ""
  description = "Kubernetes Secret name containing the Auth0/OIDC client secret. The secret value itself is provisioned out-of-band."
}

variable "auth0_client_secret_secret_key" {
  type        = string
  default     = "client-secret"
  description = "Key inside auth0_client_secret_secret_name for AQP_AUTH_OIDC_CLIENT_SECRET."
}

variable "auth_scim_bearer_token_hash_secret_name" {
  type        = string
  default     = ""
  description = "Kubernetes Secret name containing the SCIM bearer token hash. The secret value itself is provisioned out-of-band."
}

variable "auth_scim_bearer_token_hash_secret_key" {
  type        = string
  default     = "token-hash"
  description = "Key inside auth_scim_bearer_token_hash_secret_name for AQP_AUTH_SCIM_BEARER_TOKEN_HASH."
}
