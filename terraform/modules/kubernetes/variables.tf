variable "cloud_provider" {
  description = "Target cloud (local | aws | gcp | azure)."
  type        = string
}

variable "environment" {
  type = string
}

variable "cluster_name" {
  type    = string
  default = ""
}

variable "region" {
  type    = string
  default = ""
}

variable "node_instance_type" {
  type    = string
  default = "t3.large"
}

variable "node_min_count" {
  type    = number
  default = 1
}

variable "node_max_count" {
  type    = number
  default = 5
}

variable "common_tags" {
  type    = map(string)
  default = {}
}

variable "install_helm_baseline" {
  description = "When true, install the cert-manager / ESO / KEDA / ingress-nginx / kube-prometheus / otel-operator / istio baseline."
  type        = bool
  default     = true
}
