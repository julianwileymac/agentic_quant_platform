###############################################################################
# Wiley Tech — Entra ID internal tenant (Workstream "Entra internal tenant").
#
# Brings the AQP staff Entra tenant under Terraform control. The
# detailed plan lives at docs/plans/entra-internal-tenant-rollout.md;
# the module README at
# ../../modules/aqp_entra_directory/README.md.
#
# AGENTS rule 27 — runtime identity flows through MSALEntraIdentityProvider.
# AGENTS rule 42 — apply path is TerraformRuntime via ``aqp deploy``.
# AGENTS rule 44 — EntraTenantLink approval flow stays in front of any
# customer-tenant onboarding; this module is internal-only.
###############################################################################

# Pin the azuread provider for THIS environment. The shared
# versions.tf already pins it module-wide; this provider block
# supplies the runtime tenant id.
provider "azuread" {
  tenant_id = var.entra_tenant_id
}

variable "entra_tenant_id" {
  type        = string
  description = "AQP staff Entra tenant id. Sourced from TF_VAR_entra_tenant_id (Vault)."
  default     = ""
}

variable "entra_tenant_primary_domain" {
  type        = string
  description = "Primary domain of the AQP staff Entra tenant (e.g. wiley-tech.onmicrosoft.com)."
  default     = "wiley-tech.onmicrosoft.com"
}

variable "entra_enabled" {
  type        = bool
  description = "Master switch for the aqp_entra_directory module. Keep false until the Phase 1 plan-only review has completed."
  default     = false
}

module "aqp_entra_directory" {
  source = "../../modules/aqp_entra_directory"

  enabled               = var.entra_enabled
  tenant_id             = var.entra_tenant_id
  tenant_primary_domain = var.entra_tenant_primary_domain
  display_name_prefix   = "AQP"

  staff_app = {
    name        = "aqp-staff"
    description = "AQP staff login app for manage.aqp.fund."
    redirect_uris = [
      "https://manage.aqp.fund/api/auth/entra/callback",
      "http://localhost:3001/api/auth/entra/callback",
    ]
    logout_urls = [
      "https://manage.aqp.fund",
      "http://localhost:3001",
    ]
    web_origins = [
      "https://manage.aqp.fund",
    ]
    sign_in_audience = "AzureADMyOrg"
  }
  # The defaults from variables.tf cover manage_api_app, ci_app,
  # ci_federated_credentials, named_locations, and ca_policy_references.
  # Override here only if the wiley-tech environment needs a deviation.
}

output "entra_tenant_id" {
  value       = module.aqp_entra_directory.tenant_id
  description = "Echo of the Entra tenant id under Terraform control."
}

output "entra_staff_app_client_id" {
  value       = module.aqp_entra_directory.staff_app_client_id
  description = "Application (client) id of the AQP staff login app. Plumb into AQP_AUTH_MSAL_INTERNAL_APP_ID."
}

output "entra_manage_api_client_id" {
  value       = module.aqp_entra_directory.manage_api_client_id
  description = "Application (client) id of the AQP manage API Resource Server."
}

output "entra_manage_api_identifier_uri" {
  value       = module.aqp_entra_directory.manage_api_identifier_uri
  description = "Identifier URI of the manage API. Audience claim of staff access tokens."
}

output "entra_ci_app_client_id" {
  value       = module.aqp_entra_directory.ci_app_client_id
  description = "Application (client) id of the GitHub Actions OIDC federation app."
}

output "entra_summary" {
  value       = module.aqp_entra_directory.summary
  description = "Compact summary suitable for the helper scripts."
}
