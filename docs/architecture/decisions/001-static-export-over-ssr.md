# ADR 001 — Static export (Vite) over SSR for the AQP client surface

- **Status**: Accepted (2026-05-18)
- **Authors**: Platform team
- **Supersedes**: None
- **Related**: [ADR 002 — single container client](002-single-container-client.md), [`frontend/CUTOVER.md`](../../../frontend/CUTOVER.md)

## Context

The AQP frontend rewrite (`frontend/`, Vite 7 + React 19 + Tailwind 4 + shadcn/ui) is the cutover-complete operator UI. The legacy `webui/` (Next.js 15 / antd) remains in tree only as a rollback path. The new `aqp_client` container needs to bundle a UI build, the legacy fallback, and the FastAPI gateway into a single deployable image.

Three rendering options were considered for the canonical UI:

1. **Server-side rendering (Next.js)** — server-rendered React with client-side hydration, mounted under uvicorn via `WSGIMiddleware`.
2. **Static export (Next.js)** — `next build` with `output: 'export'`, identical to the prompt's original §2.1 wording.
3. **Static export (Vite)** — `pnpm --dir frontend build` emitting a single `dist/` static SPA bundle.

## Decision

The canonical UI shipped in `aqp_client` is the **Vite static export** under `frontend/`. The Next.js legacy `webui/` is mounted as a rollback surface at `/webui` and Solara at `/legacy`, but neither is the default landing page.

Concretely:

- Stage 1 of `/build/docker/aqp_client/Dockerfile` runs `pnpm --dir frontend build` and copies `frontend/dist/` to `/app/static/`.
- The FastAPI app in `aqp/api/main.py` mounts `/static` to the Vite asset directory and falls back to `index.html` for client-side routes (SPA fallback).
- The Vite app calls API endpoints through a relative `/api` prefix; the FastAPI gateway proxies those to whatever the `ConnectivityConfig` env vars point at.

## Consequences

**Positive**
- Single-process Python runtime — no Node.js in the production image, smaller attack surface, no `npm` supply-chain risk in production.
- No SSR cold-start cost. The whole UI is ~3 MB of static assets served with `Cache-Control: immutable`.
- Identical container in dev, k3d, and Kubernetes — only env vars change.
- Vite is already canonical per [`frontend/CUTOVER.md`](../../../frontend/CUTOVER.md). Picking the in-flight stack avoids reopening the cutover debate.

**Negative**
- No streaming-SSR for the operator UI. WebSocket and SSE streams (chat, live, telemetry) carry the live data instead, which matches the existing throttled `useChatStream` / `useLiveStream` hooks.
- SEO and first-paint metrics are weaker than SSR, but the AQP UI is an authenticated operator console, not a public site — neither matters.
- Pre-rendered routes per user/tenant are not possible. All personalisation happens client-side using Auth0 claims from `useUser()`.

## Alternatives considered

- **SSR** — rejected because it forces Node.js into the runtime image and adds a separate process to supervise.
- **Static export (Next.js)** — rejected to avoid maintaining two frontend toolchains. The Next.js webui stays as rollback only.

## Implementation references

- Frontend build target: `frontend/package.json` `"build": "vite build"`
- Production Dockerfile: `build/docker/aqp_client/Dockerfile`
- SPA fallback handler: `aqp/api/main.py::serve_spa`
- Cutover history: [`frontend/CUTOVER.md`](../../../frontend/CUTOVER.md)
