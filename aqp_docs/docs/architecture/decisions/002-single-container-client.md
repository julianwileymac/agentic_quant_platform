---
title: 'ADR 002 — Single multi-stage container for the AQP client surface'
summary: 'Today AQP runs the Vite frontend on `:3001` (compose `:3002`), the legacy Next.js webui on `:3000` (now stopped), the legacy Solara UI on `:8765`, and the FastAPI API on `:8000`. Operators have to jug...'
owner: platform-team
last_reviewed: 2026-05-25
audience: both
---

# ADR 002 — Single multi-stage container for the AQP client surface

- **Status**: Accepted (2026-05-18) — **Superseded for `aqp_ui` by [ADR 011](011-cdn-fronted-standalone-for-aqp-ui.md) on 2026-05-25.** Still in force for the local-operator `aqp_client/` packaging path.
- **Authors**: Platform team
- **Supersedes**: None
- **Superseded by**: [ADR 011 — CDN-fronted standalone for `aqp_ui`](011-cdn-fronted-standalone-for-aqp-ui.md) (cloud surface only)
- **Related**: [ADR 001 — Vite static export](001-static-export-over-ssr.md), [ADR 005 — separated control plane](005-separated-control-plane.md), [ADR 011 — CDN-fronted standalone for `aqp_ui`](011-cdn-fronted-standalone-for-aqp-ui.md), [ADR 012 — Solara deprecation](012-solara-deprecation.md)

> **Scope narrowing (2026-05-25):** This ADR's decisions apply ONLY
> to the local-operator `aqp_client/` packaging. The cloud-hosted
> `aqp_ui/` surface (at `aqp.fund` / `app.aqp.fund`) is governed by
> ADR 011 and uses a clean Next.js standalone container with no
> ASGI proxy stage. See ADR 011 for the cloud rationale.

## Context

Today AQP runs the Vite frontend on `:3001` (compose `:3002`), the legacy Next.js webui on `:3000` (now stopped), the legacy Solara UI on `:8765`, and the FastAPI API on `:8000`. Operators have to juggle four URLs and four health probes. The `aqp_client` Docker image is a chance to collapse these into one.

Three packaging options were considered:

1. **One container per surface** — separate `aqp-frontend`, `aqp-solara`, `aqp-api` images; an external Ingress/NGINX layer fans traffic.
2. **Sidecar pattern** — one Pod per surface, sharing localhost via an `nginx` sidecar.
3. **Single multi-stage build** — Stage 1 builds Vite, Stage 2 prepares Solara, Stage 3 (production) is a `python:3.11-slim` runtime that serves both as static + ASGI mount and proxies API traffic.

## Decision

`aqp_client` is **one image built from a three-stage Dockerfile** that ships:

- Stage 1 (`ui-builder`, `node:20-alpine`) — runs `pnpm --dir aqp_client build`, output to `/app/out/`. Node is dropped after this stage.
- Stage 2 (`solara-builder`, `python:3.11-slim`) — installs Solara + legacy UI deps, pre-warms component caches, verifies `legacy_ui.app` is importable.
- Stage 3 (`production`, `python:3.11-slim`) — installs FastAPI + uvicorn + httpx + websockets + python-jose + `aqp_platform_core`. Copies Vite assets from Stage 1 and Solara from Stage 2. Exposes port `8080`. No Node, no npm.

The Stage 3 runtime mounts:

- `/static` → Vite assets from Stage 1
- `/legacy` → Solara ASGI app
- `/webui` → legacy Next.js export (rollback only)
- `/api/*` → reverse-proxied to `AQP_CORE_API_URL`
- `/ml/*` → reverse-proxied to `AQP_ML_API_URL`
- `/mcp/*` → reverse-proxied to `AQP_MCP_URL`
- `/manage/*` → reverse-proxied to `AQP_CONTROL_PLANE_URL`
- `/ws/*` → WebSocket proxy with reconnect-with-backoff

## Consequences

**Positive**
- One image, one health probe (`/health`), one set of `securityContext` rules.
- Stable URL surface for operators — bookmarks, dashboards, and runbooks don't break when backends move.
- All backend addresses live in `ConnectivityConfig` env vars. The same image runs in compose with `AQP_*_URL=http://aqp-core:8000` or in K8s with `http://aqp-core.default.svc.cluster.local`.
- Auth0 callback URLs stay constant. The Vite app sees one origin; the FastAPI proxy injects M2M `Authorization` headers for cross-service calls.
- Smaller blast radius. The control plane is a separate container on a separate Docker network (`aqp-admin` vs `aqp-internal`) — they only talk over the proxy.

**Negative**
- Builds are larger and slower than per-surface images. Mitigated by Docker layer caching and buildx (~3 min cold, ~30s incremental).
- Scaling assumes Vite + Solara + proxy throughput grow together. In practice Vite assets are CDN-fronted by NGINX Ingress and the proxy is the bottleneck — a single container HPA on CPU is fine.
- Rolling back to webui-only or Solara-only means env-flag toggles (`AQP_CLIENT_ENABLE_LEGACY_UI`, `AQP_CLIENT_ENABLE_SOLARA`) rather than swapping deployments.

## Alternatives considered

- **One container per surface** — rejected. Adds 3 health probes, 3 Ingress rules, 3 image tags to keep in lockstep on every release. The operator experience regresses.
- **Sidecar pattern** — rejected. Mixing sidecars + multi-process supervision in one Pod adds significant Pod-startup ordering risk for marginal CPU savings.

## Implementation references

- Multi-stage Dockerfile: `aqp_platform/build/docker/aqp_client/Dockerfile`
- FastAPI proxy: `aqp/api/proxy.py`
- WebSocket proxy with reconnect: `aqp/api/ws/proxy.py`
- ConnectivityConfig: `aqp_platform_core/connectivity/config.py`
