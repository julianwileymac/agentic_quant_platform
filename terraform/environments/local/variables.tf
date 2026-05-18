###############################################################################
# Local environment variables. Defaults match the docker-compose port
# layout so tools that hard-code :8000 (api), :3001 (frontend dev),
# :5000 (mlflow), :16686 (jaeger) keep working.
###############################################################################

variable "environment" {
  type    = string
  default = "local"
}

variable "namespace" {
  type        = string
  default     = "aqp-local"
  description = "Kubernetes namespace AQP services land in. Matches the canonical aqp-local slot."
}

variable "cluster_name" {
  type    = string
  default = "aqp-local"
}

variable "app_version" {
  type        = string
  default     = "latest"
  description = "Image tag for the aqp-* container images. Bump to publish a new build."
}

variable "registry_port" {
  type        = number
  default     = 5001
  description = "Localhost port the k3d-managed registry binds to. Cluster pulls from aqp-registry:5001."
}

variable "lb_http_port" {
  type        = number
  default     = 8000
  description = "Host port mapped to Traefik :80 (the AQP API + frontend ingress lands here)."
}

variable "lb_https_port" {
  type        = number
  default     = 3001
  description = "Host port mapped to Traefik :443."
}

variable "local_shell_interpreter" {
  type        = string
  default     = "bash"
  description = "Shell executable used by Terraform local-exec. Set to Git Bash on Windows."
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
  description = "Deployment topology service IDs enabled for this target."
}
