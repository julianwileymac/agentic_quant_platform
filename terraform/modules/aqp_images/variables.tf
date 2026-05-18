###############################################################################
# aqp_images — inputs.
###############################################################################

variable "cloud_provider" {
  type        = string
  description = "Active cloud provider. Image build only fires on local/docker."
}

variable "registry_host" {
  type        = string
  description = "Registry host:port the cluster pulls from (e.g. aqp-registry:5001)."
}

variable "registry_localhost" {
  type        = string
  description = "Registry host:port reachable from the host shell (e.g. localhost:5001)."
}

variable "context_path" {
  type        = string
  description = "Repository root used as the docker build context. The environment composition passes path.cwd or a relative ../../../."
}

variable "app_version" {
  type        = string
  default     = "latest"
  description = "Image tag (typically the AQP app_version)."
}

variable "frontend_dist_path" {
  type        = string
  default     = "frontend/dist"
  description = "Relative path (under context_path) to the built Vite bundle. The frontend Dockerfile expects this directory."
}

variable "ready_marker" {
  type        = string
  default     = ""
  description = "Pseudo-input wired from local_cluster.ready so the build only runs after the cluster + registry are up."
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
