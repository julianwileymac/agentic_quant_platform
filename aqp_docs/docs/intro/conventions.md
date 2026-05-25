---
title: 'Conventions'
summary: 'Documentation authoring rules, frontmatter contract, and how to ship a new doc.'
owner: docs-team
last_reviewed: 2026-05-25
audience: both
sidebar_position: 5
---

# Conventions

## Frontmatter is mandatory

Every `.md` or `.mdx` file under `aqp_docs/docs/` MUST have a
frontmatter block validated by the Zod schema at
[src/lib/frontmatterSchema.ts](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp_docs/src/lib/frontmatterSchema.ts).

Required fields:

- `title` — the human-readable title (becomes the `<h1>`).
- `summary` — a one-liner consumed by `/llms.txt` and the search
  index. Keep under 200 characters.
- `owner` — the GitHub Team that owns the page (`platform-team`,
  `docs-team`, `data-team`, `rl-team`, `ml-team`, `agentic-team`,
  `strategy-team`, `trading-team`, `identity-team`, `infra-team`,
  `sre-team`).
- `last_reviewed` — ISO 8601 date. The stale-content watchdog opens
  a GitHub Issue when this is more than 180 days old.
- `audience` — one of `human`, `agent`, `both`, `internal`.

Optional:

- `version` — pin to a specific date-epoch.
- `deprecated`, `deprecated_replacement`, `deprecated_at`,
  `deprecated_sunset` — deprecation lifecycle (Stripe-style epochs).
- `keywords`, `tags`, `sidebar_label`, `sidebar_position`,
  `runnable` — Docusaurus-native fields.

## Cross-linking

Use relative markdown links. The autolink resolver in Docusaurus
maps them to the published routes at build time.

```mdx
See [the data plane concept](../concepts/data/data-plane.md) for the
provider → cache → DuckDB view pipeline.
```

Cite source code with a full absolute repo URL:

```mdx
[aqp/data/iceberg_catalog.py](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp/data/iceberg_catalog.py)
```

Do not link to specific line numbers — they bit-rot quickly.

## Diagrams

Mermaid only. GitHub renders it natively; Docusaurus ships
`@docusaurus/theme-mermaid` which renders it client-side here.

Do not commit PNG / SVG diagrams unless they are screenshots of a
running UI and are time-stamped.

## Code blocks

Tag every code block with a language. Tag runnable blocks with the
`runnable` attribute; Phase 5 of the migration will render those
with a "Run" button backed by Pyodide (for Python) or StackBlitz
WebContainers (for JS / TS).

```python runnable
import requests
print(requests.get("http://localhost:8000/readyz").status_code)
```

## "Was this helpful?"

Every page renders the feedback widget from
[src/components/FeedbackWidget.tsx](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp_docs/src/components/FeedbackWidget.tsx).
Submissions POST to a Cloudflare Worker that opens a `docs-feedback`
GitHub Issue tagged with the page's CODEOWNER team.

## Editing this page

Click the "Edit this page" link at the bottom — it opens
github.dev for a browser-side edit. Or open the PR locally:

```powershell
git checkout -b docs/fix-typo
# edit
git add aqp_docs/docs/...
git commit -m "docs: fix typo in quickstart"
git push -u origin docs/fix-typo
```

Branch protection requires the docs-CI suite to pass plus one
CODEOWNER approval.

## Business editors

Non-engineers can edit content through Keystatic at
[https://docs.aqp.fund/keystatic](/keystatic). Keystatic stores
changes in Git and opens a PR against `main`. No parallel CMS,
no duplicate database.

## AI agents

Read `/llms.txt` for the curated index, `/llms-full.txt` for the
full corpus, or query the MCP server at `/mcp`. The MCP server is
RFC 9728 + 8707-compliant (AQP rule 49) and validates the `aud`
claim against `AQP_MCP_DOCS_CANONICAL_URI`.
