variable "enabled" {
  type        = bool
  default     = false
  description = "When false, every resource in this module is disabled. Keep false until aqp_ui is ready to claim its production hostnames."
}

variable "domain" {
  type        = string
  default     = ""
  description = "Auth0 tenant domain (e.g. aqp-fund.us.auth0.com). Provider auth uses the AUTH0_DOMAIN/AUTH0_CLIENT_ID/AUTH0_CLIENT_SECRET env vars."
}

variable "app_name" {
  type    = string
  default = "AQP UI (Cloud)"
}

variable "app_description" {
  type    = string
  default = "Cloud-hosted, multi-tenant PaaS frontend for the Agentic Quant Platform."
}

variable "api_identifier" {
  type        = string
  default     = "https://api.aqp.internal/manage"
  description = "Auth0 Resource Server identifier this SPA's access tokens are minted against. Must match the existing aqp_identity API resource."
}

variable "callback_urls" {
  type = list(string)
  default = [
    "https://aqp.fund/api/auth/auth0/callback",
    "https://www.aqp.fund/api/auth/auth0/callback",
    "https://app.aqp.fund/api/auth/auth0/callback",
    "http://localhost:3002/api/auth/auth0/callback",
  ]
}

variable "logout_urls" {
  type = list(string)
  default = [
    "https://aqp.fund",
    "https://www.aqp.fund",
    "https://app.aqp.fund",
    "http://localhost:3002",
  ]
}

variable "web_origins" {
  type = list(string)
  default = [
    "https://aqp.fund",
    "https://www.aqp.fund",
    "https://app.aqp.fund",
    "http://localhost:3002",
  ]
}

variable "claims_namespace" {
  type    = string
  default = "https://aqp.internal/"
}

# -----------------------------------------------------------------------------
# Entra (B2B SSO) optional resources.
#
# These require the `hashicorp/azuread` provider, which is NOT currently
# pinned in aqp_platform/terraform/versions.tf. When enabled, add the
# provider block and `terraform init` to pick it up.
# -----------------------------------------------------------------------------
variable "entra_enabled" {
  type    = bool
  default = false
}

variable "entra_display_name" {
  type    = string
  default = "AQP Cloud (multi-tenant)"
}

variable "entra_redirect_uris" {
  type = list(string)
  default = [
    "https://aqp.fund/api/auth/entra/callback",
    "https://www.aqp.fund/api/auth/entra/callback",
    "https://app.aqp.fund/api/auth/entra/callback",
  ]
}
