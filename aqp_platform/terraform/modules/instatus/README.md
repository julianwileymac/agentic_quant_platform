# `instatus` Terraform module

Provisions the status page at `status.aqp.fund` on Instatus, the
matching Cloudflare DNS CNAME, the default service components
mirroring `aqp_platform/configs/deployment/topology.yaml`, and the
Slack incident webhook.

## Why a separate zone

The status page MUST stay up when AQP is degraded. Per the
blueprint: "status page lives at `status.<product>.com` — separate
hostname, separate Cloudflare zone, so it stays up when other
infrastructure is degraded." We use the same `aqp.fund` Cloudflare
zone but with `proxied = false` so the request goes straight to
Instatus's own edge.

## Usage

```hcl
module "status" {
  source = "../../modules/instatus"

  account_id        = var.cloudflare_account_id
  zone_id           = var.cloudflare_zone_id_aqp_fund
  instatus_api_key  = var.instatus_api_key
  instatus_org_id   = var.instatus_org_id
  slack_webhook_url = var.slack_oncall_webhook
}
```

All variables flow through `CredentialResolver` (AGENTS rule 26).

## Status banner integration

The docs site renders a live banner on every page via the
[`StatusBanner.tsx`](../../../../aqp_docs/src/components/StatusBanner.tsx)
component. It polls `https://status.aqp.fund/summary.json` every
60 s (cached at the Cloudflare edge per
`aqp_docs/docusaurus.config.ts` `themeConfig.instatus.cacheTtlSeconds`).
