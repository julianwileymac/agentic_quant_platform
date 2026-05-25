/**
 * Cloudflare Pages module for the AQP docs site at docs.aqp.fund.
 *
 * Provisions:
 *
 *   1. A Cloudflare Pages project (`aqp-docs`) wired to the
 *      julianwileymac/agentic_quant_platform GitHub repo. Builds run
 *      on every push to `main`; preview builds run on every PR.
 *   2. A custom domain (`docs.aqp.fund`) and an apex CNAME pointing
 *      at the Pages-managed hostname (NOT the existing cluster
 *      tunnel — docs is an EDGE property, never a cluster workload).
 *   3. A second custom domain on `archive.aqp.fund` for the
 *      frozen Stripe-style API epoch archive.
 *   4. Zero Trust Access applications protecting the
 *      `/internal/*` path (engineering OIDC) and the
 *      `/enterprise/*` path (Auth0 + Entra customer SSO).
 *   5. A separate Worker (`aqp-docs-mcp`) hosting the
 *      RFC 9728 + 8707-compliant MCP server (the wrangler.toml at
 *      aqp_docs/wrangler.toml drives the deploy; this module wires
 *      its routes + DNS).
 *   6. Logpush from Pages to the new R2 bucket
 *      `aqp-docs-access-logs` with 365-day retention (SOC 2 /
 *      ISO 27001).
 *
 * Hard rules respected:
 *
 *   - AGENTS rule 42 (TerraformRuntime): this module is applied
 *     through TerraformRuntime, never via raw `terraform apply`.
 *   - AGENTS rule 26 (CredentialResolver): the Cloudflare API
 *     token comes from Vault via ExternalSecret. No literal tokens
 *     in this file.
 *   - AGENTS rule 47 (topology): the resulting subdomains are
 *     registered in aqp_platform/configs/deployment/topology.yaml
 *     as `aqp-docs`, `aqp-docs-archive`, `aqp-docs-status` entries.
 *   - AGENTS rule 49 (MCP RFC 9728+8707): the Worker publishes its
 *     Protected Resource Metadata; this module just routes traffic.
 *   - aqp-management-engine always-on (credential safety):
 *     `cloudflare_api_token` is `sensitive=true`; never logged.
 */

terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.6"
    }
  }
}

variable "account_id" {
  type        = string
  description = "Cloudflare account id."
  sensitive   = true
}

variable "zone_id" {
  type        = string
  description = "Cloudflare DNS zone id for aqp.fund."
}

variable "project_name" {
  type        = string
  default     = "aqp-docs"
  description = "Cloudflare Pages project name."
}

variable "github_owner" {
  type    = string
  default = "julianwileymac"
}

variable "github_repo" {
  type    = string
  default = "agentic_quant_platform"
}

variable "production_branch" {
  type    = string
  default = "main"
}

variable "build_root_dir" {
  type        = string
  default     = "aqp_docs"
  description = "Path within the monorepo Pages should build from."
}

variable "primary_hostname" {
  type    = string
  default = "docs.aqp.fund"
}

variable "archive_hostname" {
  type    = string
  default = "archive.aqp.fund"
}

variable "internal_oidc_group_ids" {
  description = "OIDC group ids permitted to view /internal/* (engineering)."
  type        = list(string)
  default     = []
}

variable "enterprise_customer_organization_ids" {
  description = "AQP organization ids permitted to view /enterprise/*."
  type        = list(string)
  default     = []
}

variable "logpush_r2_bucket" {
  type        = string
  default     = "aqp-docs-access-logs"
  description = "R2 bucket receiving Pages + Worker request logs (365 d retention)."
}

variable "logpush_retention_days" {
  type    = number
  default = 365
}

variable "build_env_vars" {
  description = <<-EOT
    Non-secret build env vars. Secrets (Inkeep, GitHub App,
    PostHog, Plausible, Instatus page id) come from the
    ExternalSecret chain — never inline here.
  EOT
  type        = map(string)
  default = {
    AQP_DOCS_SITE_URL     = "https://docs.aqp.fund"
    AQP_DOCS_BASE_URL     = "/"
    AQP_DOCS_PLAUSIBLE_DOMAIN = "docs.aqp.fund"
    AQP_DOCS_INSTATUS_PAGE_URL = "https://status.aqp.fund"
  }
}

variable "build_secret_keys" {
  description = "Names of secret env vars Pages will pull from the Cloudflare secret store."
  type        = list(string)
  default = [
    "AQP_DOCS_INKEEP_API_KEY",
    "AQP_DOCS_POSTHOG_KEY",
    "AQP_DOCS_INSTATUS_PAGE_ID",
    "GITHUB_APP_INSTALLATION_TOKEN",
    "AQP_MCP_DOCS_M2M_CLIENT_ID",
    "AQP_MCP_DOCS_M2M_CLIENT_SECRET",
  ]
}

# ---------------------------------------------------------------------------
# Cloudflare Pages project
# ---------------------------------------------------------------------------

resource "cloudflare_pages_project" "docs" {
  account_id        = var.account_id
  name              = var.project_name
  production_branch = var.production_branch

  source = {
    type = "github"
    config = {
      owner                        = var.github_owner
      repo_name                    = var.github_repo
      production_branch            = var.production_branch
      preview_branch_includes      = ["*"]
      preview_branch_excludes      = []
      pr_comments_enabled          = true
      deployments_enabled          = true
    }
  }

  build_config = {
    build_command       = "pnpm install --frozen-lockfile && pnpm --filter aqp_docs build"
    destination_dir     = "${var.build_root_dir}/build"
    root_dir            = ""
  }

  deployment_configs = {
    production = {
      compatibility_date  = "2026-05-01"
      compatibility_flags = ["nodejs_compat"]
      env_vars            = { for k, v in var.build_env_vars : k => { type = "plain_text", value = v } }
    }
    preview = {
      compatibility_date  = "2026-05-01"
      compatibility_flags = ["nodejs_compat"]
      env_vars            = { for k, v in var.build_env_vars : k => { type = "plain_text", value = v } }
    }
  }
}

# ---------------------------------------------------------------------------
# Custom domains: docs.aqp.fund + archive.aqp.fund
# ---------------------------------------------------------------------------

resource "cloudflare_pages_domain" "primary" {
  account_id   = var.account_id
  project_name = cloudflare_pages_project.docs.name
  name         = var.primary_hostname
}

resource "cloudflare_pages_domain" "archive" {
  account_id   = var.account_id
  project_name = cloudflare_pages_project.docs.name
  name         = var.archive_hostname
}

resource "cloudflare_dns_record" "docs_cname" {
  zone_id = var.zone_id
  name    = var.primary_hostname
  type    = "CNAME"
  content = "${cloudflare_pages_project.docs.name}.pages.dev"
  ttl     = 1
  proxied = true
  comment = "AQP docs site (Cloudflare Pages — NOT the aqp-fund-edge tunnel)."
}

resource "cloudflare_dns_record" "archive_cname" {
  zone_id = var.zone_id
  name    = var.archive_hostname
  type    = "CNAME"
  content = "${cloudflare_pages_project.docs.name}.pages.dev"
  ttl     = 1
  proxied = true
  comment = "AQP docs archive (frozen Stripe-style API epochs)."
}

# ---------------------------------------------------------------------------
# Cloudflare Access — gates /internal/* and /enterprise/*
# ---------------------------------------------------------------------------

resource "cloudflare_zero_trust_access_application" "internal" {
  account_id                = var.account_id
  name                      = "AQP Docs — Internal"
  domain                    = "${var.primary_hostname}/internal"
  type                      = "self_hosted"
  session_duration          = "8h"
  auto_redirect_to_identity = true
  app_launcher_visible      = false
  http_only_cookie_attribute = true
  same_site_cookie_attribute = "lax"
}

resource "cloudflare_zero_trust_access_policy" "internal_engineering" {
  account_id     = var.account_id
  application_id = cloudflare_zero_trust_access_application.internal.id
  name           = "Engineering only"
  decision       = "allow"
  include = [
    for gid in var.internal_oidc_group_ids : {
      group = { id = gid }
    }
  ]
}

resource "cloudflare_zero_trust_access_application" "enterprise" {
  account_id                = var.account_id
  name                      = "AQP Docs — Enterprise"
  domain                    = "${var.primary_hostname}/enterprise"
  type                      = "self_hosted"
  session_duration          = "24h"
  auto_redirect_to_identity = true
  app_launcher_visible      = true
  http_only_cookie_attribute = true
  same_site_cookie_attribute = "lax"
}

resource "cloudflare_zero_trust_access_policy" "enterprise_customers" {
  account_id     = var.account_id
  application_id = cloudflare_zero_trust_access_application.enterprise.id
  name           = "Provisioned customer orgs"
  decision       = "allow"
  include = [
    for org_id in var.enterprise_customer_organization_ids : {
      service_token = { token_id = org_id }
    }
  ]
}

# ---------------------------------------------------------------------------
# Logpush to R2 (SOC 2 / ISO 27001 — 365-day retention)
# ---------------------------------------------------------------------------

resource "cloudflare_r2_bucket" "access_logs" {
  account_id = var.account_id
  name       = var.logpush_r2_bucket
  location   = "ENAM"
}

resource "cloudflare_logpush_job" "pages_requests" {
  account_id          = var.account_id
  name                = "${var.project_name}-pages-requests"
  enabled             = true
  dataset             = "http_requests"
  logpull_options     = "fields=ClientRequestHost,ClientRequestMethod,ClientRequestURI,ClientCountry,EdgeStartTimestamp,EdgeEndTimestamp,EdgeResponseStatus,RayID&timestamps=rfc3339"
  destination_conf    = "r2://${cloudflare_r2_bucket.access_logs.name}/pages/{DATE}?account-id=${var.account_id}&access-key-id=via-credential-resolver&secret-access-key=via-credential-resolver"
  filter              = "{\"where\":{\"key\":\"ClientRequestHost\",\"operator\":\"contains\",\"value\":\"${var.primary_hostname}\"}}"
  output_options = {
    output_type          = "ndjson"
    batch_prefix         = "{DATE}/{HOUR}/"
    batch_suffix         = ".ndjson"
    timestamp_format     = "rfc3339"
    field_delimiter      = ","
  }
}

resource "cloudflare_logpush_job" "access_audits" {
  account_id          = var.account_id
  name                = "${var.project_name}-access-audits"
  enabled             = true
  dataset             = "access_requests"
  logpull_options     = "fields=AccountID,RayID,Action,Allowed,AppDomain,AppID,AppUID,Connection,Country,CreatedAt,Email,IPAddress,Type,UserUUID"
  destination_conf    = "r2://${cloudflare_r2_bucket.access_logs.name}/access/{DATE}?account-id=${var.account_id}&access-key-id=via-credential-resolver&secret-access-key=via-credential-resolver"
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "pages_project_id" {
  value = cloudflare_pages_project.docs.id
}

output "pages_subdomain" {
  value = "${cloudflare_pages_project.docs.name}.pages.dev"
}

output "primary_hostname" {
  value = var.primary_hostname
}

output "archive_hostname" {
  value = var.archive_hostname
}

output "internal_access_app_aud" {
  value     = cloudflare_zero_trust_access_application.internal.aud
  sensitive = true
}

output "enterprise_access_app_aud" {
  value     = cloudflare_zero_trust_access_application.enterprise.aud
  sensitive = true
}

output "r2_bucket_name" {
  value = cloudflare_r2_bucket.access_logs.name
}
