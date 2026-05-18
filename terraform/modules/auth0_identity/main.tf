terraform {
  required_providers {
    auth0 = {
      source  = "auth0/auth0"
      version = "~> 1.11"
    }
  }
}

locals {
  scopes = [
    { value = "data:read", description = "Read AQP data and metadata" },
    { value = "data:write", description = "Mutate AQP data through sanctioned APIs" },
    { value = "deploy:run", description = "Run Terraform/Kubernetes deployments" },
    { value = "deploy:halt", description = "Halt AQP deployments and long-running runtimes" },
    { value = "scim:write", description = "Provision AQP users and groups through SCIM" },
  ]
}

resource "auth0_client" "spa" {
  count           = var.enabled ? 1 : 0
  name            = var.spa_name
  app_type        = "spa"
  oidc_conformant = true

  callbacks                  = var.callback_urls
  allowed_logout_urls        = var.logout_urls
  web_origins                = var.web_origins
  grant_types                = ["authorization_code", "refresh_token"]
  token_endpoint_auth_method = "none"
}

resource "auth0_resource_server" "api" {
  count                                           = var.enabled ? 1 : 0
  name                                            = var.api_name
  identifier                                      = var.api_identifier
  token_lifetime                                  = 86400
  enforce_policies                                = true
  skip_consent_for_verifiable_first_party_clients = true

  dynamic "scopes" {
    for_each = local.scopes
    content {
      value       = scopes.value.value
      description = scopes.value.description
    }
  }
}

resource "auth0_client" "m2m" {
  count           = var.enabled ? 1 : 0
  name            = "AQP SCIM + Auth0 Sync M2M"
  app_type        = "non_interactive"
  oidc_conformant = true
  grant_types     = ["client_credentials"]
}

resource "auth0_client_grant" "m2m_api" {
  count     = var.enabled ? 1 : 0
  client_id = auth0_client.m2m[0].client_id
  audience  = auth0_resource_server.api[0].identifier
  scopes    = ["data:read", "scim:write", "deploy:run", "deploy:halt"]
}

resource "auth0_role" "viewer" {
  count       = var.enabled ? 1 : 0
  name        = "aqp-viewer"
  description = "Read-only AQP operator"
}

resource "auth0_role" "admin" {
  count       = var.enabled ? 1 : 0
  name        = "aqp-admin"
  description = "AQP administrator"
}

resource "auth0_action" "post_login_claims" {
  count   = var.enabled && var.auth0_sync_url != "" ? 1 : 0
  name    = "AQP post-login claims sync"
  runtime = "node22"
  deploy  = true

  supported_triggers {
    id      = "post-login"
    version = "v3"
  }

  code = templatefile("${path.module}/post_login_action.js.tftpl", {
    sync_url         = var.auth0_sync_url
    api_audience     = var.api_identifier
    claims_namespace = var.claims_namespace
  })
}
