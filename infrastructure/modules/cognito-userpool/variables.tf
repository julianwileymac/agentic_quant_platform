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
  description = "Common tags applied to every resource."
}

variable "vpc_id" {
  type        = string
  default     = null
  description = "Unused for Cognito (managed service) but kept for uniform module contract."
}

variable "private_subnet_ids" {
  type        = list(string)
  default     = []
  description = "Unused for Cognito (managed service) but kept for uniform module contract."
}

variable "kms_key_arn" {
  type        = string
  default     = null
  description = "Unused (Cognito uses AWS-owned keys for managed encryption)."
}

variable "callback_urls" {
  type        = list(string)
  description = "OIDC redirect URIs for the SPA + ALB OIDC integration."
}

variable "logout_urls" {
  type        = list(string)
  default     = []
  description = "OIDC RP-initiated logout URIs."
}

variable "mfa_configuration" {
  type        = string
  default     = "OPTIONAL"
  description = "Cognito MFA mode — OFF | OPTIONAL | ON. AGENTS rule 52 prefers ON for prod."
}

variable "advanced_security_mode" {
  type        = string
  default     = "ENFORCED"
  description = "Cognito advanced security — OFF | AUDIT | ENFORCED."
}

variable "invite_only" {
  type        = bool
  default     = false
  description = "When true, only admins can create users (admin-managed onboarding)."
}

variable "create_identity_pool" {
  type        = bool
  default     = false
  description = "When true, also create an Identity Pool for federated AWS credential vending."
}
