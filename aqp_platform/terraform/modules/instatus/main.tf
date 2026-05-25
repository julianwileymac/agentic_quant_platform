/**
 * Instatus status-page module for status.aqp.fund.
 *
 * Instatus is a managed status-page SaaS. They expose a REST API
 * but no official Terraform provider, so this module uses the
 * `restapi` provider against the documented endpoints
 * (https://instatus.com/help/api).
 *
 * Provisions:
 *
 *   1. The status page itself at status.aqp.fund (separate zone for
 *      incident-time resilience — must stay up when the rest of the
 *      stack is degraded).
 *   2. The CNAME record at the Cloudflare zone pointing at the
 *      Instatus-managed hostname.
 *   3. The default components mirroring the topology.yaml services
 *      (aqp-core, aqp-cp, aqp-client, paper-trading, …).
 *   4. The Slack + email webhooks for incident broadcasts.
 *
 * Hard rules respected:
 *
 *   - AGENTS rule 42 (TerraformRuntime) — applied via
 *     `aqp deploy --stack status-page`, never raw `terraform apply`.
 *   - AGENTS rule 26 (CredentialResolver) — `instatus_api_key`
 *     and `slack_webhook_url` resolve via the secret store.
 *   - aqp-management-engine always-on — sensitive args are marked
 *     `sensitive = true`; values never logged.
 *   - Domain isolation — status.aqp.fund is on the same aqp.fund
 *     zone as the rest of AQP. NOT julianwiley.com.
 */

terraform {
  required_providers {
    cloudflare = { source = "cloudflare/cloudflare", version = "~> 5.6" }
    restapi    = { source = "Mastercard/restapi", version = "~> 1.19" }
  }
}

variable "account_id" {
  type      = string
  sensitive = true
}

variable "zone_id" {
  type        = string
  description = "Cloudflare DNS zone id for aqp.fund."
}

variable "instatus_api_key" {
  type      = string
  sensitive = true
}

variable "instatus_org_id" {
  type = string
}

variable "hostname" {
  type    = string
  default = "status.aqp.fund"
}

variable "page_name" {
  type    = string
  default = "AQP"
}

variable "slack_webhook_url" {
  type      = string
  default   = ""
  sensitive = true
}

variable "primary_components" {
  description = <<-EOT
    Status-page components mirroring the topology.yaml service list.
    Each item: { id, name, description, group, role }.
  EOT
  type = list(object({
    id          = string
    name        = string
    description = string
    group       = string
  }))
  default = [
    { id = "aqp-core",    name = "AQP Core API",         description = "Public API at api.aqp.fund",          group = "API" },
    { id = "aqp-cp",      name = "AQP Control Plane",    description = "Workload lifecycle at manage.aqp.fund", group = "API" },
    { id = "aqp-client",  name = "Operator UI",          description = "Vite frontend at aqp.fund",            group = "Frontend" },
    { id = "aqp-ui",      name = "Cloud Frontend (PaaS)", description = "Next.js cloud-hosted UI",             group = "Frontend" },
    { id = "aqp-docs",    name = "Docs (edge)",          description = "docs.aqp.fund (Cloudflare Pages)",     group = "Frontend" },
    { id = "data",        name = "Data plane",           description = "Iceberg, Postgres, pgvector, Redis",  group = "Data" },
    { id = "agents",      name = "Agent runtime",        description = "Agent / RL / workflow execution",      group = "Compute" },
    { id = "paper",       name = "Paper trading",        description = "Simulated execution + risk overlays",  group = "Trading" },
    { id = "kafka",       name = "Streaming",            description = "Redpanda + Flink",                     group = "Data" },
  ]
}

# ---------------------------------------------------------------------------
# REST API provider — pointed at Instatus.
# ---------------------------------------------------------------------------

provider "restapi" {
  alias                = "instatus"
  uri                  = "https://api.instatus.com"
  write_returns_object = true
  headers = {
    "Authorization" = "Bearer ${var.instatus_api_key}"
    "Content-Type"  = "application/json"
  }
}

# ---------------------------------------------------------------------------
# Status page.
# ---------------------------------------------------------------------------

resource "restapi_object" "page" {
  provider = restapi.instatus
  path     = "/v2/${var.instatus_org_id}/pages"
  id_attribute = "id"

  data = jsonencode({
    name      = var.page_name
    subdomain = "aqp"           # default *.instatus.com fallback
    language  = "en"
    timezone  = "UTC"
    customDomain = var.hostname
    layout    = "boxes"
    publicVisible = true
  })
}

# Default components mirroring the service catalogue.
resource "restapi_object" "components" {
  provider = restapi.instatus
  for_each = { for c in var.primary_components : c.id => c }

  path = "/v2/${var.instatus_org_id}/pages/${restapi_object.page.id}/components"
  id_attribute = "id"

  data = jsonencode({
    name        = each.value.name
    description = each.value.description
    group       = each.value.group
    showUptime  = true
    status      = "OPERATIONAL"
  })
}

# Slack webhook for incidents (optional).
resource "restapi_object" "slack_webhook" {
  count    = var.slack_webhook_url == "" ? 0 : 1
  provider = restapi.instatus
  path     = "/v2/${var.instatus_org_id}/pages/${restapi_object.page.id}/integrations"
  id_attribute = "id"

  data = jsonencode({
    type        = "slack"
    name        = "AQP On-call"
    webhookUrl  = var.slack_webhook_url
  })
}

# ---------------------------------------------------------------------------
# DNS — CNAME status.aqp.fund -> *.instatus.com.
# ---------------------------------------------------------------------------

resource "cloudflare_dns_record" "status_cname" {
  zone_id = var.zone_id
  name    = var.hostname
  type    = "CNAME"
  content = "aqp.instatus.com"
  ttl     = 1
  proxied = false  # Cloudflare-proxied breaks Instatus's TLS termination.
  comment = "status.aqp.fund -> Instatus (separate zone for incident-time resilience)."
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "page_id" {
  value = restapi_object.page.id
}

output "hostname" {
  value = var.hostname
}

output "summary_json_url" {
  value = "https://${var.hostname}/summary.json"
  description = "Public JSON endpoint the docs StatusBanner component polls every 60 s."
}
