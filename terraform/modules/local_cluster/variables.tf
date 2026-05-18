###############################################################################
# local_cluster — inputs.
###############################################################################

variable "cloud_provider" {
  type        = string
  description = "Active AQP cloud provider. Resources only provision when this equals 'local' or 'docker'."
}

variable "environment" {
  type        = string
  description = "Environment slug (typically 'local')."
}

variable "cluster_name" {
  type        = string
  default     = "aqp-local"
  description = "k3d cluster name (idempotent — re-applies are no-ops)."
}

variable "k3d_image" {
  type        = string
  default     = "rancher/k3s:v1.30.4-k3s1"
  description = "k3s image used by k3d under the hood."
}

variable "registry_name" {
  type        = string
  default     = "aqp-registry"
  description = "k3d-managed image registry name. Maps to localhost:<registry_port>."
}

variable "registry_port" {
  type        = number
  default     = 5001
  description = "Localhost port the k3d registry binds to."
}

variable "lb_http_port" {
  type        = number
  default     = 8000
  description = "Host port mapped to the cluster Traefik HTTP loadbalancer."
}

variable "lb_https_port" {
  type        = number
  default     = 3001
  description = "Host port mapped to the cluster Traefik HTTPS loadbalancer."
}

variable "kubeconfig_path" {
  type        = string
  default     = "~/.kube/aqp-local.config"
  description = "Path the module writes the merged kubeconfig to. The local environment composition points provider \"kubernetes\".config_path at this file."
}

variable "local_shell_interpreter" {
  type        = string
  default     = "bash"
  description = "Shell executable for local-exec blocks. On Windows prefer Git Bash, e.g. C:/Program Files/Git/bin/bash.exe, to avoid WSL bash shims."
}

variable "common_tags" {
  type    = map(string)
  default = {}
}
