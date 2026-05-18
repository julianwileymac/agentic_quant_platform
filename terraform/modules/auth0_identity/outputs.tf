output "enabled" {
  value = var.enabled
}

output "spa_client_id" {
  value       = var.enabled ? auth0_client.spa[0].client_id : ""
  description = "Auth0 SPA application client id."
}

output "api_identifier" {
  value       = var.enabled ? auth0_resource_server.api[0].identifier : var.api_identifier
  description = "AQP API audience."
}

output "m2m_client_id" {
  value       = var.enabled ? auth0_client.m2m[0].client_id : ""
  description = "Auth0 M2M client id for SCIM/Auth0 sync."
}

output "post_login_action_id" {
  value       = var.enabled && var.auth0_sync_url != "" ? auth0_action.post_login_claims[0].id : ""
  description = "Auth0 post-login Action id."
}
