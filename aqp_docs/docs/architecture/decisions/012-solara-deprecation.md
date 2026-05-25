---
title: 'ADR 012 — Solara deprecation in the cloud build'
summary: 'Solara is excluded from the cloud aqp_ui Dockerfile and remains only in the local aqp_client image for one-release-cycle rollback. The Solara stage will be removed entirely from aqp_client after the rollback window closes.'
owner: platform-team
last_reviewed: 2026-05-25
audience: both
---

# ADR 012 — Solara deprecation in the cloud build

- **Status**: Accepted (2026-05-25)
- **Authors**: Platform team
- **Related**: [ADR 002 — Single multi-stage container](002-single-container-client.md), [ADR 011 — CDN-fronted standalone for aqp_ui](011-cdn-fronted-standalone-for-aqp-ui.md)

## Context

The legacy Solara UI (`legacy_ui.app` at
[`aqp/ui/`](../../../aqp/ui/)) is a Python ASGI presentation layer
that predates the Vite + React 19 + shadcn cutover documented in
[`aqp_client/CUTOVER.md`](../../../aqp_client/CUTOVER.md). It is
already wrapped in the `legacy` profile and gated behind
`AQP_CLIENT_ENABLE_SOLARA` (ADR 002 Stage 2 + production runtime).

The cloud `aqp_ui/` Next.js application has no need for Solara —
every chart that Solara renders is already covered by the
`lightweight-charts` / `recharts` stack already in
[`aqp_client/package.json`](../../../aqp_client/package.json) and
inherited by `aqp_ui/`. Continuing to bundle Solara into the cloud
image is pure dead weight (~300 MB) AND it creates a second
presentation-layer state machine the BFF would otherwise have to
synchronise with the React component tree.

## Decision

1. **`aqp_ui/` Dockerfile excludes Solara entirely** (already the
   case). No `solara-builder` stage; no `/legacy` mount.
2. **`aqp_client/` retains the Solara stage for one release cycle
   beyond Phase 1 of the cloud-dash refactor.** This preserves the
   ADR 002 rollback contract.
3. **After one release cycle, the Solara stage is removed from
   `aqp_client/`** (Phase 7 of the cloud-dash refactor plan):
   - Delete the `solara-builder` stage from
     [`aqp_platform/build/docker/aqp_client/Dockerfile`](../../../aqp_platform/build/docker/aqp_client/Dockerfile).
   - Drop the `/legacy` mount from the Stage-3 FastAPI proxy.
   - Remove `AQP_CLIENT_ENABLE_SOLARA` from
     [`aqp/config/settings.py`](../../../aqp/config/settings.py).
   - `git mv aqp/ui/ aqp/legacy_solara_ui/` so the source code
     remains for archaeological reference but no longer ships.
4. **No new Solara work.** The `legacy` profile is in maintenance
   mode only. New visualisation lands in `aqp_client/` (Vite +
   shadcn) or `aqp_ui/` (Next.js + antd + recharts).

## Consequences

**Positive**

- Cloud image stays small (~150 MB) and Python-free; cold-start
  latency is dominated by Next.js startup, not Solara warmup.
- One less presentation-layer state machine to keep in sync with
  the React component tree.
- Bundle audits stop having to explain why a TypeScript-first PaaS
  ships a 300 MB Python interpreter.

**Negative**

- Operators who relied on Solara dashboards have to migrate before
  the Phase-7 removal. The migration is well-documented: every
  Solara surface has a Vite analog (see the cutover checklist in
  [`aqp_client/CUTOVER.md`](../../../aqp_client/CUTOVER.md)).
- Loss of Solara's Python-side reactive component model. This was
  an interesting prototype path but not a load-bearing operator
  workflow.

## Alternatives considered

- **Keep Solara indefinitely as a "second UI"** — rejected. The
  cost of maintaining two parallel presentation stacks (React +
  Solara) outweighs the value of an alternate visualisation
  framework that no current workflow needs.
- **Port Solara to JupyterLab embed** — rejected. JupyterLab is
  intended for notebook authoring (Lab Engine), not operator
  dashboards. Mixing the two surfaces would re-create the original
  framework-fragmentation problem ADR 002 set out to solve.

## Implementation references

- ADR 002 Solara stage: [`aqp_platform/build/docker/aqp_client/Dockerfile`](../../../aqp_platform/build/docker/aqp_client/Dockerfile) (Stage 2 `solara-builder`)
- Solara source: [`aqp/ui/`](../../../aqp/ui/)
- Feature flag: `AQP_CLIENT_ENABLE_SOLARA` in [`aqp/config/settings.py`](../../../aqp/config/settings.py)
- Cutover history: [`aqp_client/CUTOVER.md`](../../../aqp_client/CUTOVER.md)
- Phase-7 removal step: [`.cursor/plans/aqp_cloud-hosted_dash_refactor_*.plan.md`](../../../.cursor/plans/)
