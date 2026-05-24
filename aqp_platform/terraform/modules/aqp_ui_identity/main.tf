terraform {
  required_providers {
    auth0 = {
      source  = "auth0/auth0"
      version = "~> 1.11"
    }
  }
}

# -----------------------------------------------------------------------------
# Auth0 Regular Web Application for aqp_ui.
#
# AGENTS rule 27 — identity flows through the existing IdentityProvider
# chain. This module only provisions the Auth0-side client. The session
# cookie is signed by aqp_ui itself; M2M token exchange against the
# Resource Server (api_identifier) uses the existing aqp_identity
# module's API + M2M client.
# -----------------------------------------------------------------------------
resource "auth0_client" "aqp_ui" {
  count = var.enabled ? 1 : 0

  name                = var.app_name
  description         = var.app_description
  app_type            = "regular_web"
  callbacks           = var.callback_urls
  allowed_logout_urls = var.logout_urls
  web_origins         = var.web_origins
  cross_origin_auth   = false
  oidc_conformant     = true
  grant_types = [
    "authorization_code",
    "refresh_token",
    "implicit",
  ]
  custom_login_page_on = false
  is_first_party       = true
  jwt_configuration {
    alg                 = "RS256"
    lifetime_in_seconds = 36000
    secret_encoded      = false
  }
  refresh_token {
    expiration_type              = "expiring"
    rotation_type                = "rotating"
    token_lifetime               = 2592000 # 30 days
    idle_token_lifetime          = 1296000 # 15 days
    leeway                       = 0
    infinite_token_lifetime      = false
    infinite_idle_token_lifetime = false
  }
}

resource "auth0_client_grant" "aqp_ui_api" {
  count = var.enabled ? 1 : 0

  client_id = auth0_client.aqp_ui[0].client_id
  audience  = var.api_identifier
  scopes = [
    "data:read",
    "data:write",
    "trade:read",
    "trade:execute",
    "agent:view",
    "agent:execute",
    "agent:terminate",
    "backtest:read",
    "backtest:create",
    "rag:query",
    "read:timeseries",
    "ml:workbench",
    "rl:train",
    "manage:agents",
    "deploy:halt",
    "workloads:halt",
    "tenancy:invite",
  ]
}

# -----------------------------------------------------------------------------
# Microsoft Entra ID (Azure AD) Application Registration for B2B SSO.
#
# Wired ONLY when var.entra_enabled = true AND the `azuread` provider is
# pinned in aqp_platform/terraform/versions.tf. AGENTS rule 44 keeps the
# `EntraTenantLink` approval flow in front of any actual organization
# provisioning — this resource just creates the app registration that
# customers' Entra tenants consent to.
#
# The matching ENTRA_CLIENT_SECRET is generated out-of-band and written
# to Vault at secret/data/aqp-ui/entra by an operator (or by a separate
# `azuread_application_password` resource if your CI runs with Graph API
# permissions).
# -----------------------------------------------------------------------------
# Uncomment when azuread provider is pinned:
#
# resource "azuread_application" "aqp_ui" {
#   count            = var.enabled && var.entra_enabled ? 1 : 0
#   display_name     = var.entra_display_name
#   sign_in_audience = "AzureADMultipleOrgs"
#
#   web {
#     redirect_uris = var.entra_redirect_uris
#     implicit_grant {
#       access_token_issuance_enabled = false
#       id_token_issuance_enabled     = false
#     }
#   }
#
#   required_resource_access {
#     resource_app_id = "00000003-0000-0000-c000-000000000000" # Microsoft Graph
#
#     resource_access {
#       id   = "e1fe6dd8-ba31-4d61-89e7-88639da4683d" # User.Read
#       type = "Scope"
#     }
#     resource_access {
#       id   = "37f7f235-527c-4136-accd-4a02d197296e" # openid
#       type = "Scope"
#     }
#     resource_access {
#       id   = "14dad69e-099b-42c9-810b-d002981feec1" # profile
#       type = "Scope"
#     }
#     resource_access {
#       id   = "64a6cdd6-aab1-4aaf-94b8-3cc8405e90d0" # email
#       type = "Scope"
#     }
#   }
# }
