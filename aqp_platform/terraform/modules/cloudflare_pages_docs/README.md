# `cloudflare_pages_docs` Terraform module

Provisions the Cloudflare Pages edge property at `docs.aqp.fund`,
the matching `archive.aqp.fund` for sunset API epochs, the two
Cloudflare Access applications gating `/internal/*` and
`/enterprise/*`, the R2 bucket receiving access logs, and the two
Logpush jobs that ship request + Access audit logs there.

## Usage

```hcl
module "docs" {
  source = "../../modules/cloudflare_pages_docs"

  account_id = data.aws_secretsmanager_secret_version.cf_account_id.secret_string
  zone_id    = data.aws_secretsmanager_secret_version.cf_zone_id_aqp_fund.secret_string

  internal_oidc_group_ids = [
    var.engineering_okta_group_id,
  ]

  enterprise_customer_organization_ids = [
    # Populated by data.tenancy.list_orgs MCP tool at apply time
    # via the TerraformRuntime spec hydration step.
  ]
}
```

## Hard rules

- **AGENTS rule 42 (TerraformRuntime).** Apply via
  `aqp deploy --stack docs-edge` (which lands a `terraform_runs`
  row), never raw `terraform apply`.
- **AGENTS rule 43 (hash-locked spec versions).** The matching
  `TerraformStackSpec` lives at
  [`aqp_platform/configs/terraform/prod.yaml`](../../../configs/terraform/prod.yaml);
  re-snapshotting on hash change creates a new
  `terraform_stack_spec_versions` row.
- **AGENTS rule 47 (topology).** The hostnames provisioned here
  (`docs.aqp.fund`, `archive.aqp.fund`) are registered in
  [`aqp_platform/configs/deployment/topology.yaml`](../../../configs/deployment/topology.yaml).
- **AGENTS rule 26 (CredentialResolver).** Every secret arg
  resolves through Vault via the ExternalSecret chain. No
  literal tokens in module variable files.
- **Edge-not-cluster.** The Pages project is intentionally NOT
  routed through the existing `aqp-fund-edge` Cloudflare Tunnel
  in [`aqp_platform/deployments/kubernetes/edge/cloudflared-aqp/`](../../../deployments/kubernetes/edge/cloudflared-aqp/).
  When the cluster is down, docs MUST stay up.

## Resources created

- `cloudflare_pages_project.docs` — the Pages project.
- `cloudflare_pages_domain.{primary,archive}` — custom domains.
- `cloudflare_dns_record.{docs,archive}_cname` — DNS records.
- `cloudflare_zero_trust_access_application.{internal,enterprise}` —
  the two Access apps.
- `cloudflare_zero_trust_access_policy.{internal_engineering,enterprise_customers}` —
  the two allow policies.
- `cloudflare_r2_bucket.access_logs` — the audit-log bucket.
- `cloudflare_logpush_job.{pages_requests,access_audits}` — log
  streams.

## Inputs

See `main.tf`. Required: `account_id`, `zone_id`. Everything else
defaults to the production AQP shape.

## Outputs

- `pages_project_id` — the Pages project id.
- `pages_subdomain` — the underlying `<name>.pages.dev` hostname.
- `primary_hostname` / `archive_hostname` — convenience echoes.
- `internal_access_app_aud` / `enterprise_access_app_aud` — Access
  app AUD tags. Sensitive — these feed
  `aqp.auth.providers.cloudflare_access.CloudflareAccessProvider`
  via the secret-resolver chain.
- `r2_bucket_name` — confirms the audit bucket was created.

## Phase 5 follow-up

The `status.aqp.fund` Instatus provisioning lives in a sibling
module — see
[`aqp_platform/terraform/modules/instatus/`](../instatus/).
The MCP Cloudflare Worker is deployed via Wrangler from
[`aqp_docs/wrangler.toml`](../../../../aqp_docs/wrangler.toml).
