---
title: 'Internal-only docs'
summary: 'Engineering- and SRE-only docs. Cloudflare Access gated at /internal/*.'
owner: sre-team
last_reviewed: 2026-05-25
audience: internal
---

# Internal-only docs

This tree is Cloudflare Access gated — only the engineering OIDC
group can read it.

The Access app + policies are provisioned by
[`aqp_platform/terraform/modules/cloudflare_pages_docs/main.tf`](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp_platform/terraform/modules/cloudflare_pages_docs/main.tf).

## What lives here

- [Monthly content audit](./audit/index.mdx)
- (More to be added — see the cross-cut-content-depth todo.)

## Why a separate path

Some operational and audit content is genuinely internal:

- Customer-org-specific incident postmortems.
- Engineering process docs.
- Audit dashboards driven by PostHog data we cannot expose
  publicly.

Each page also carries `audience: internal` in its frontmatter, so
the llms.txt + MCP corpora deliberately exclude it.

## Audit logs

Every authenticated request to `/internal/*` lands in the
`aqp-docs-access-logs` R2 bucket via the
`cloudflare_logpush_job.access_audits` Terraform resource.
Retention: 365 days (SOC 2 / ISO 27001).
