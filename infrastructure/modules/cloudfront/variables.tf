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
  default     = null
  description = "Unused (CloudFront is global); kept for uniform module contract."
}

variable "private_subnet_ids" {
  type        = list(string)
  default     = []
}

variable "kms_key_arn" {
  type        = string
  default     = null
}

variable "alb_dns_name" {
  type        = string
  description = "ALB DNS name (from modules/alb.dns_name) — used as the CloudFront origin."
}

variable "aliases" {
  type        = list(string)
  description = "Alternate domain names for the distribution (e.g. admin.aqp.fund)."
}

variable "acm_certificate_arn" {
  type        = string
  description = "ACM certificate ARN in us-east-1 (CloudFront requirement) for the aliases."
}

variable "waf_web_acl_arn" {
  type        = string
  default     = null
  description = "Optional WAFv2 web ACL ARN to attach (AWSManagedRulesCommonRuleSet etc.)."
}

variable "access_logs_bucket_domain" {
  type        = string
  default     = null
  description = "Optional S3 bucket DOMAIN (not name) for access logs."
}

variable "origin_secret_header_value" {
  type        = string
  description = "Shared secret injected as X-CloudFront-Secret so the ALB can reject direct hits."
  sensitive   = true
}

variable "price_class" {
  type        = string
  default     = "PriceClass_100"
  description = "CloudFront price class — PriceClass_100 (NA+EU) is the cheapest, PriceClass_All ($$$)."
}

variable "geo_restriction_type" {
  type        = string
  default     = "none"
  description = "none | whitelist | blacklist."
}

variable "geo_restriction_locations" {
  type        = list(string)
  default     = []
  description = "Country codes when geo_restriction_type != 'none'."
}
