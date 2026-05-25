---
title: 'ADR 011 — CDN-fronted standalone container for the cloud-hosted aqp_ui'
summary: 'The cloud-hosted Next.js 14 PaaS frontend (aqp_ui) ships as a clean Next.js standalone container at app.aqp.fund. Static assets are CDN-fronted by Cloudflare. ADR 002''s multi-stage Solara/Vite/ASGI proxy pattern is scoped to the local aqp_client only.'
owner: platform-team
last_reviewed: 2026-05-25
audience: both
---

# ADR 011 — CDN-fronted standalone container for the cloud-hosted aqp_ui

- **Status**: Accepted (2026-05-25)
- **Authors**: Platform team
- **Supersedes (scoped)**: [ADR 002 — Single multi-stage container for the AQP client surface](002-single-container-client.md) for the cloud surface only; ADR 002 stays in force for the local `aqp_client/` Vite operator UI.
- **Related**: [ADR 001 — Vite static export](001-static-export-over-ssr.md), [ADR 002 — Single multi-stage container](002-single-container-client.md), [ADR 003 — Auth0 zero-trust](003-auth0-zero-trust.md), [ADR 005 — Separated control plane](005-separated-control-plane.md), [ADR 012 — Solara deprecation](012-solara-deprecation.md)

## Context

When the original `aqp_client/` packaging was designed (ADR 002), the
platform had three coexisting presentation surfaces: a Vite operator
UI, a legacy Next.js webui, and a Python Solara visualisation layer.
Collapsing all three behind one FastAPI proxy was the right call for
a single-tenant local-first deployment where operators bookmark one
URL and the proxy hides the rest.

The cloud-hosted, customer-facing PaaS at `aqp.fund` /
`app.aqp.fund` (the new `aqp_ui/` Next.js 14+ App Router app) has
different constraints:

1. **Multi-tenant scale.** Hundreds-to-thousands of concurrent
   tenants. Static-asset throughput and SSR throughput scale at
   different ratios — co-located scaling triggers wasted CPU and
   unnecessary memory pressure on the SSR pods.
2. **CDN-friendly assets.** Next.js standalone emits hashed,
   immutable filenames under `/_next/static/*`. Serving them from
   the SSR pods is bandwidth waste; Cloudflare can cache them for a
   year with zero risk of staleness.
3. **No Python / no Solara.** `aqp_ui/` is pure TypeScript + Next.js
   server. The Solara stage (ADR 002 Stage 2) doesn't apply and
   would only bloat the image (~300 MB heavier).
4. **Independent BFF lifecycle.** Every `aqp_ui/api/*` route is a
   thin BFF handler that re-checks the session, forwards a tenancy
   header, and proxies upstream. Reverse-proxying through FastAPI
   adds an extra hop with no value (the BFF is already a proxy).
5. **Edge-rendered marketing.** The `(marketing)` route group is
   designed for SSR + ISR cache. Routing it through an internal
   FastAPI proxy defeats the whole point of edge-near rendering.

## Decision

The cloud-hosted `aqp_ui` ships as **one clean Next.js standalone
container** built from
[`aqp_platform/build/docker/aqp_ui/Dockerfile`](../../../aqp_platform/build/docker/aqp_ui/Dockerfile)
(already two stages: `node:20-alpine` builder + `node:20-alpine`
runtime running `node server.js`). It DOES NOT use the ADR 002
three-stage Python/ASGI pattern.

**Edge caching layout:**

| Path                  | Cache-Control                                            | Notes |
| --------------------- | -------------------------------------------------------- | ----- |
| `/_next/static/*`     | `public, max-age=31536000, immutable`                    | Hashed filenames; year-long TTL |
| `/public/*` `/fonts/*` `/images/*` | `public, max-age=2592000`                | 30-day TTL, hand-curated assets |
| `/api/*`              | `no-store` + `Pragma: no-cache`                          | BFF responses; user-scoped (rule 4 + management-engine.mdc) |
| Everything else (SSR) | `public, max-age=3600, stale-while-revalidate=86400`     | Per-tenant marketing + dashboard pages |

The NGINX Ingress at
[`aqp_platform/deployments/kubernetes/base/aqp-ui/ingress.yaml`](../../../aqp_platform/deployments/kubernetes/base/aqp-ui/ingress.yaml)
sets these via `nginx.ingress.kubernetes.io/configuration-snippet`.
Cloudflare in front honours them aggressively for `/_next/static/*`
and bypasses the cache for `/api/*`.

**Post-deploy cache purge:** the GitHub Actions deploy job in
[`.github/workflows/aqp-ui.yml`](../../../.github/workflows/aqp-ui.yml)
calls the Cloudflare zone-purge API immediately after
`kubectl rollout status` succeeds. The Cloudflare token is sourced
from the existing `CredentialResolver` chain via the
`AQP_CLOUDFLARE_API_TOKEN` ExternalSecret (AGENTS rule 26).

**HPA:** keep the existing
[`hpa.yaml`](../../../aqp_platform/deployments/kubernetes/base/aqp-ui/hpa.yaml)
(CPU 70%, memory 80%, 3-20 replicas). Because static assets are
CDN-offloaded, SSR pod CPU usage tracks real per-tenant rendering
work — autoscaling becomes meaningful instead of a noisy mix of
"serving a JS bundle" and "rendering a dashboard page".

## Consequences

**Positive**

- 80%+ static-asset bandwidth offloaded to Cloudflare's edge.
- HPA triggers on real SSR work, not bandwidth.
- Image is ~150 MB (Node Alpine) vs. ~450 MB (Python + Solara +
  Node) for ADR 002. Faster pod cold start, faster rolling deploys.
- The BFF + SSR + edge layers have one ownership boundary each —
  Cloudflare for delivery, NGINX Ingress for cache hints,
  `node server.js` for SSR + BFF. No ASGI proxy hop in between.
- `/api/*` is `no-store` end-to-end — no risk of a CDN edge node
  caching a tenant's response and serving it to a different tenant.

**Negative**

- Two presentation packaging stories now exist (ADR 002 for
  `aqp_client`, ADR 011 for `aqp_ui`). Mitigated by the per-surface
  scoping: each ADR is the source of truth for one tree only.
- Cloudflare cache-purge is now part of the deploy critical path. A
  Cloudflare API outage during deploy means stale `/_next/static/*`
  for up to 1y per hashed filename — but the hashes change on every
  deploy, so the impact is bounded to assets whose names didn't
  change (rare for a real change).
- Adds a `CLOUDFLARE_API_TOKEN` secret to the deploy environment.
  Stored in Vault + synced via ExternalSecret per AGENTS rule 26.

## Alternatives considered

- **Stay on ADR 002 (single FastAPI proxy container)** — rejected.
  Bandwidth-CPU coupling, larger image, unnecessary Solara/Python
  weight, redundant proxy hop in front of the BFF.
- **Vercel hosting** — rejected. ADR 003's zero-trust constraints
  + the on-cluster control plane integration argue for keeping the
  SSR layer inside our own K8s + CredentialResolver perimeter.
- **CloudFront in front of a single SSR pod** — rejected. We
  already have Cloudflare as the edge for `aqp.fund`. Adding a
  second CDN would split the cache-purge story and add edge cost.

## Implementation references

- Standalone Dockerfile: [`aqp_platform/build/docker/aqp_ui/Dockerfile`](../../../aqp_platform/build/docker/aqp_ui/Dockerfile)
- Ingress + CDN headers: [`aqp_platform/deployments/kubernetes/base/aqp-ui/ingress.yaml`](../../../aqp_platform/deployments/kubernetes/base/aqp-ui/ingress.yaml)
- HPA: [`aqp_platform/deployments/kubernetes/base/aqp-ui/hpa.yaml`](../../../aqp_platform/deployments/kubernetes/base/aqp-ui/hpa.yaml)
- CI deploy + cache purge: [`.github/workflows/aqp-ui.yml`](../../../.github/workflows/aqp-ui.yml)
- BFF + session: [`aqp_ui/src/lib/auth/session.ts`](../../../aqp_ui/src/lib/auth/session.ts), [`aqp_ui/src/lib/api/client.ts`](../../../aqp_ui/src/lib/api/client.ts)
