# Cloudflare Workers + Pages Functions

This directory houses three Pages Functions and one stand-alone
Cloudflare Worker that ship alongside the static Docusaurus build.

## Pages Functions

- [`md-negotiation/`](md-negotiation/) — content negotiation on
  `Accept: text/markdown`. Routes `/*` (every page).
- [`page-fragment/`](page-fragment/) — sanitised `<article>` HTML
  for the in-product `<DocsPanel />`. Route `/api/page/:id`.
- [`feedback/`](feedback/) — "Was this helpful?" → GitHub Issue.
  Route `/api/feedback` (POST only).

The Pages Functions are wired up automatically by Cloudflare Pages
during build; their file paths under `workers/` mirror the routes
when deployed.

> Pages Functions traditionally live under `functions/`. The
> [`aqp_platform/terraform/modules/cloudflare_pages_docs/`](../../aqp_platform/terraform/modules/cloudflare_pages_docs/)
> module sets `pages_build_config.functions_directory = "aqp_docs/workers"`.

## Stand-alone Worker

- [`mcp/`](mcp/) — RFC 9728 + 8707-compliant Model Context Protocol
  server. Deployed as a separate Worker so it can be scaled,
  rotated, and (in Phase 4) re-targeted behind Cloudflare Access
  without re-deploying the docs site itself.

The Worker is published to a separate route (`docs.aqp.fund/mcp`)
via the same Terraform module. Its wrangler config lives at
[`wrangler.toml`](../wrangler.toml).

## Local development

```powershell
cd aqp_docs
pnpm install
# Dev server for the Docusaurus app (Pages Functions auto-mount):
pnpm dev
# Or run a single Worker locally:
wrangler dev workers/mcp/index.ts
```

## Hard rules

- AQP rule 26 (CredentialResolver) — every secret env var comes
  from Vault via ExternalSecret on the Pages build env.
- AQP rule 49 (MCP RFC 9728/8707) — the MCP Worker publishes
  Protected Resource Metadata and validates the `aud` claim.
- `aqp-management-engine` always-on (credential safety) — no
  Authorization header / bearer / token value is ever logged.
