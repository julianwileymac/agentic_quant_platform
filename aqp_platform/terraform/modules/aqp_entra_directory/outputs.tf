# =============================================================================
# aqp_entra_directory — outputs
#
# Outputs are consumed by:
#   * scripts/identity/seed_entra_internal_tenant.py (writes the
#     EntraTenantLink row in Postgres + the matching Vault paths).
#   * Settings layer (auth_msal_internal_tenant_id /
#     auth_msal_internal_app_id) at deploy time.
#   * .github/workflows/entra-terraform.yml — Vault-write + smoke test.
# =============================================================================

output "tenant_id" {
  value       = var.tenant_id
  description = "Echo of the Entra tenant id under management. Stable across plans."
}

output "tenant_primary_domain" {
  value       = var.tenant_primary_domain
  description = "Echo of the tenant primary domain (e.g. wiley-tech.onmicrosoft.com)."
}

output "staff_app_client_id" {
  value       = try(azuread_application.staff[0].client_id, "")
  description = "Application (client) id of the AQP staff login app."
}

output "staff_app_object_id" {
  value       = try(azuread_application.staff[0].object_id, "")
  description = "Object id of the AQP staff login app — used by the rotate-secret helper."
}

output "manage_api_client_id" {
  value       = try(azuread_application.manage_api[0].client_id, "")
  description = "Application (client) id of the AQP manage API Resource Server."
}

output "manage_api_identifier_uri" {
  value       = var.manage_api_app.identifier_uri
  description = "Identifier URI of the manage API. Tokens minted for this audience carry the ``roles`` claim."
}

output "ci_app_client_id" {
  value       = try(azuread_application.ci_github[0].client_id, "")
  description = "Application (client) id of the GitHub Actions OIDC federation app."
}

output "ci_app_object_id" {
  value       = try(azuread_application.ci_github[0].object_id, "")
  description = "Object id of the CI federation app — for editing federated-credential subjects after the fact."
}

output "group_object_ids" {
  value = var.enabled ? {
    for k, g in azuread_group.groups : k => g.object_id
  } : {}
  description = "Map of group ``key`` (from var.groups) to Entra group object id."
}

output "app_role_ids" {
  value       = { for r in var.app_role_definitions : r.value => r.id }
  description = "Map of role ``value`` (the string in the ``roles`` claim) to its Entra UUID."
}

output "named_location_ids" {
  value = var.enabled ? {
    for k, l in azuread_named_location.ip_ranges : k => l.id
  } : {}
  description = "Map of named-location display name to Entra named-location id. Used by Security to attach CA policies."
}

output "ca_policies_documented" {
  value       = local.ca_policy_documentation
  description = "List of CA policies the operator promises exist out-of-band. The verify_entra_login helper queries Microsoft Graph to confirm each one."
}

output "summary" {
  value = {
    tenant_id                  = var.tenant_id
    tenant_primary_domain      = var.tenant_primary_domain
    staff_app_client_id        = try(azuread_application.staff[0].client_id, "")
    manage_api_client_id       = try(azuread_application.manage_api[0].client_id, "")
    manage_api_identifier      = var.manage_api_app.identifier_uri
    ci_app_client_id           = try(azuread_application.ci_github[0].client_id, "")
    group_count                = length(var.enabled ? azuread_group.groups : {})
    role_count                 = length(var.app_role_definitions)
    federated_credential_count = length(var.enabled ? azuread_application_federated_identity_credential.ci_github : {})
  }
  description = "Compact summary suitable for the helper scripts to print."
}
