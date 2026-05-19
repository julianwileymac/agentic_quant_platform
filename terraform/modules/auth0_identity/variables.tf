variable "enabled" {
  type        = bool
  default     = false
  description = "When false, every resource in this module is disabled."
}

variable "domain" {
  type        = string
  default     = ""
  description = "Auth0 tenant domain. Provider auth uses AUTH0_DOMAIN / AUTH0_CLIENT_ID / AUTH0_CLIENT_SECRET env vars."
}

variable "spa_name" {
  type    = string
  default = "AQP Frontend"
}

variable "api_name" {
  type    = string
  default = "AQP Backend API"
}

variable "api_identifier" {
  type    = string
  default = "https://api.aqp.internal/manage"
}

variable "callback_urls" {
  type    = list(string)
  default = []
}

variable "logout_urls" {
  type    = list(string)
  default = []
}

variable "web_origins" {
  type    = list(string)
  default = []
}

variable "scim_base_url" {
  type        = string
  default     = ""
  description = "Base URL to the AQP SCIM endpoint, e.g. https://aqp.example.com/scim/v2. Empty keeps SCIM documented but not embedded in actions."
}

variable "auth0_sync_url" {
  type        = string
  default     = ""
  description = "URL for /_internal/auth0/sync called by the post-login Action."
}

variable "claims_namespace" {
  type    = string
  default = "https://aqp.internal/"
}
