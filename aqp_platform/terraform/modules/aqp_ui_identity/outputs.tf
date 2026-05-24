output "client_id" {
  value       = try(auth0_client.aqp_ui[0].client_id, "")
  description = "Auth0 client_id for aqp_ui. Wire to AUTH0_CLIENT_ID via External Secrets."
}

output "client_secret" {
  value       = try(auth0_client.aqp_ui[0].client_secret, "")
  description = "Auth0 client_secret for aqp_ui. AGENTS rule 4: never emit to logs, audit, or audit_details. Stored in Vault at secret/data/aqp-ui/auth0:client_secret."
  sensitive   = true
}
