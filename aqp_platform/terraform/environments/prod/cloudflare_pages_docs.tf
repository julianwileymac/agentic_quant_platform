/**
 * Wires the cloudflare_pages_docs module into the production
 * Terraform environment.
 *
 * Applied via TerraformRuntime (AGENTS rule 42):
 *
 *   aqp deploy --stack cloudflare_pages_docs --env prod
 *
 * The spec hash lands in `terraform_stack_spec_versions` (rule 43);
 * the `terraform_runs` row lands in the audit ledger (rule 45).
 */

module "cloudflare_pages_docs" {
  source = "../../modules/cloudflare_pages_docs"

  # Resolved by the CredentialResolver chain at apply time. The
  # TerraformRuntime injects these into the runner via a tmpfs-
  # mounted secret (never persists to disk; aqp-management-engine
  # credential rule).
  account_id = var.cloudflare_account_id
  zone_id    = var.cloudflare_zone_id_aqp_fund

  internal_oidc_group_ids = [
    var.engineering_oidc_group_id,
  ]

  enterprise_customer_organization_ids = []  # Populated by data.tenancy.list_orgs at hydration time.
}

output "docs_pages_subdomain" {
  value = module.cloudflare_pages_docs.pages_subdomain
}

output "docs_internal_access_app_aud" {
  value     = module.cloudflare_pages_docs.internal_access_app_aud
  sensitive = true
}
