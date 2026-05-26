variable "environment" {
  type        = string
  description = "Deployment environment (dev | staging | prod)."
}

variable "name_prefix" {
  type        = string
  default     = "aqp"
  description = "Resource-name prefix."
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Common tags."
}

variable "vpc_id" {
  type        = string
  description = "VPC the ALB lives in."
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "Public subnets across the VPC's AZs."
}

variable "private_subnet_ids" {
  type        = list(string)
  default     = []
  description = "Unused (ALB lives in public subnets) but kept for uniform module contract."
}

variable "kms_key_arn" {
  type        = string
  default     = null
  description = "Unused; ALB access logs encrypt with the bucket's CMK."
}

variable "certificate_arn" {
  type        = string
  description = "ACM certificate ARN for the HTTPS listener (issued by modules/acm-certificates)."
}

variable "access_logs_bucket" {
  type        = string
  default     = null
  description = "Optional S3 bucket for ALB access logs (replicated to log-archive)."
}

variable "enable_http_redirect" {
  type        = bool
  default     = true
  description = "When true, also create a 80 -> 443 redirect listener."
}

variable "target_groups" {
  type = map(object({
    port              = number
    protocol          = string
    health_check_path = string
  }))
  default = {
    admin = {
      port              = 8000
      protocol          = "HTTP"
      health_check_path = "/health"
    }
    agentcore_proxy = {
      port              = 9000
      protocol          = "HTTP"
      health_check_path = "/health"
    }
  }
  description = "Map of target group key -> port + protocol + health check path."
}

variable "default_target_group_key" {
  type        = string
  default     = "admin"
  description = "Key in target_groups that the default HTTPS listener forwards to."
}

variable "cognito_user_pool_arn" {
  type        = string
  description = "Cognito User Pool ARN (from modules/cognito-userpool)."
}

variable "cognito_user_pool_client_id" {
  type        = string
  description = "Cognito SPA client id (from modules/cognito-userpool.shared_client_id)."
}

variable "cognito_user_pool_domain" {
  type        = string
  description = "Cognito User Pool domain prefix (from modules/cognito-userpool)."
}

variable "cognito_protected_paths" {
  type = map(object({
    priority         = number
    path_patterns    = list(string)
    target_group_key = string
  }))
  default = {
    admin = {
      priority         = 100
      path_patterns    = ["/admin/*", "/manage/*"]
      target_group_key = "admin"
    }
    agentcore = {
      priority         = 200
      path_patterns    = ["/agentcore/*"]
      target_group_key = "agentcore_proxy"
    }
  }
  description = "Cognito-gated listener rules; the default action forwards via authenticate-cognito then forward."
}
