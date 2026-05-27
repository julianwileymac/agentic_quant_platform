variable "region" {
  type    = string
  default = "us-east-1"
}

variable "account_id" {
  type        = string
  description = "AWS account id (must match the bootstrap state account)."
}

variable "assume_role_arn" {
  type        = string
  default     = ""
  description = "Optional STS role ARN — leave empty to use the caller's session."
}

variable "external_id" {
  type      = string
  default   = ""
  sensitive = true
}

variable "name_prefix" {
  type    = string
  default = "aqp"
}

variable "environment" {
  type    = string
  default = "minimum"
}

variable "acm_certificate_arn_alb" {
  type        = string
  description = "ACM cert ARN (regional) for the HTTPS listener — issue against ALB DNS or admin.aqp.fund."
}

variable "admin_image_tag" {
  type        = string
  default     = "latest"
  description = "ECR image tag for aqp-admin."
}

variable "callback_urls" {
  type    = list(string)
  default = ["https://admin.aqp.fund/oauth/callback"]
}

variable "alb_access_logs_bucket" {
  type    = string
  default = null
}
