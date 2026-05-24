# aqp_index debt note — aqp_ui

Per the always-on rule
[.cursor/rules/aqp-index-reflect.mdc](../rules/aqp-index-reflect.mdc),
every change that touches a qualifying surface (new top-level folder,
new `.cursor/rules/*.mdc`, repo-root `AGENTS.md` edits, new
`aqp_platform/` Kustomize bundle) must reflect in `aqp_index/` — OR
drop a debt note for the next curator pass.

This commit cannot run the `aqp-index-curator` subagent in-line, so it
opens this debt note instead.

## Changed surface

- **New top-level folder**: [aqp_ui/](../../aqp_ui/) — cloud-hosted,
  multi-tenant PaaS frontend (Next.js 14+ App Router). Dual Auth0
  (B2C) + Microsoft Entra (B2B via `EntraTenantLink`) identity.
- **New rule**: [.cursor/rules/aqp-ui.mdc](../rules/aqp-ui.mdc) —
  glob `aqp_ui/**`, mirrors `aqp-client.mdc` + `aqp-admin.mdc`
  boundary contract, adds CVE-2025-29927 pinning and dual-provider
  identity rules.
- **Repo-root [AGENTS.md](../../AGENTS.md)**: new row in the
  "Repository split routing" table for `aqp_ui/`.
- **[.cursor/rules/aqp.mdc](../rules/aqp.mdc)**: new row in the
  cardinal-rules scope table.
- **[.cursor/rules/repository-boundaries.mdc](../rules/repository-boundaries.mdc)**:
  new bullets distinguishing `aqp_client/` (local) from `aqp_ui/`
  (cloud) and `aqp_admin/` (internal).
- **New Kustomize bundle**:
  [aqp_platform/deployments/kubernetes/base/aqp-ui/](../../aqp_platform/deployments/kubernetes/base/aqp-ui/)
  — Deployment, Service, HPA, PDB, NetworkPolicy, ExternalSecret,
  Ingress for `aqp.fund`, `www.aqp.fund`, `app.aqp.fund`, `ws.aqp.fund`.
- **New Dockerfile**:
  [aqp_platform/build/docker/aqp_ui/Dockerfile](../../aqp_platform/build/docker/aqp_ui/Dockerfile)
  — multi-arch Next.js standalone (node:20-alpine -> node:20-alpine).
- **New Terraform module**:
  [aqp_platform/terraform/modules/aqp_ui_identity/](../../aqp_platform/terraform/modules/aqp_ui_identity/)
  — Auth0 SPA + optional Entra app registration. Disabled by default.
- **Topology service entry**:
  [aqp_platform/configs/deployment/topology.yaml](../../aqp_platform/configs/deployment/topology.yaml)
  — added `aqp-ui` service block (namespace: `aqp-ui`, health:
  `/api/healthz`, public_url: `https://aqp.fund`).
- **New CI workflow**:
  [.github/workflows/aqp-ui.yml](../../.github/workflows/aqp-ui.yml)
  — typecheck + lint + Vitest + Next.js production build + multi-arch
  Docker push to GHCR.
- **Renovate gating**:
  [aqp_ui/renovate.json](../../aqp_ui/renovate.json) — manual approval
  on next, @auth0/nextjs-auth0, @azure/msal-node, @rjsf/antd,
  @ant-design/nextjs-registry, iron-session, jose (CVE-2025-29927
  lesson).

## What `aqp-index-curator` should refresh on its next pass

Files under `aqp_index/` that need refreshing — owned by the curator
subagent per [aqp_index/AGENTS.md](../../aqp_index/AGENTS.md):

1. `aqp_index/index.md` — top-level project index. Add `aqp_ui/` to
   the package roster between `aqp_admin/` and `aqp_index/`.
2. `aqp_index/architecture/repos.md` (or wherever the SSoT repo map
   lives) — three-way distinction between `aqp_client/` (local power
   user), `aqp_ui/` (cloud customer), `aqp_admin/` (internal staff).
3. `aqp_index/code-index/aqp_ui.md` (new file) — token-saving signature
   index for `src/app/api/*` BFF handlers, `src/lib/auth/*`,
   `src/lib/api/*`, `src/components/*`, `src/hooks/*`.
4. `aqp_index/skills/` (if a new "Adding a BFF route handler to aqp_ui"
   skill is warranted; check existing inventory first).
5. `aqp_index/subagents/` — no new subagent introduced; nothing to do.
6. `aqp_index/configs/aqp_ui.md` — env matrix from
   [aqp_ui/.env.example](../../aqp_ui/.env.example), Vault paths
   `secret/data/aqp-ui/{auth0,entra,session}`, External Secrets
   mappings.

## One-liner pointer

Per [aqp-index-reflect.mdc](../rules/aqp-index-reflect.mdc) the only
sanctioned non-curator write to `aqp_index/`-adjacent material is a
one-liner pointer in repo-root README.md / AGENTS.md. That pointer
already exists for `aqp_admin/` — the curator should mirror it for
`aqp_ui/` on the next pass.

## Trigger

Invoke the `aqp-index-curator` subagent next time someone is doing a
multi-file edit in the area. Until then, this note keeps the SSoT
debt visible to reviewers.
