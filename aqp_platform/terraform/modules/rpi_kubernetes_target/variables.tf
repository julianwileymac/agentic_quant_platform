variable "namespace" {
  type    = string
  default = "aqp"
}

variable "common_tags" {
  type    = map(string)
  default = {}
}

variable "image_pull_secret_name" {
  type    = string
  default = ""
}

variable "auth0_domain" {
  type    = string
  default = ""
}

variable "auth0_audience" {
  type    = string
  default = ""
}

variable "auth0_client_id" {
  type    = string
  default = ""
}

variable "auth_scim_m2m_audience" {
  type        = string
  default     = ""
  description = "SCIM/M2M audience used by the backend to validate provisioning tokens. Defaults to auth0_audience when blank."
}

variable "ingress_host" {
  type    = string
  default = ""
}
