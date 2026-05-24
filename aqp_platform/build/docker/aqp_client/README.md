# build/docker/aqp_client

Three-stage Dockerfile that bundles:

| Stage             | Base                  | Purpose                                                    |
| ----------------- | --------------------- | ---------------------------------------------------------- |
| `ui-builder`      | `node:20-alpine`      | `pnpm --dir aqp_client build` → static Vite bundle           |
| `solara-builder`  | `python:3.11-slim`    | Install Solara + legacy UI deps, pre-warm caches           |
| `production`      | `python:3.11-slim`    | FastAPI + uvicorn + httpx + websockets + python-jose       |

The production image exposes port **8080** and mounts:
- `/` → Vite SPA (with client-side routing fallback to `index.html`)
- `/legacy` → Solara ASGI app
- `/webui` → legacy Next.js export (rollback only)
- `/api/*` → reverse-proxied to `AQP_CORE_API_URL`
- `/ml/*` → `AQP_ML_API_URL`
- `/mcp/*` → `AQP_MCP_URL`
- `/manage/*` → `AQP_CONTROL_PLANE_URL`
- `/ws/*` → WebSocket reverse proxy with reconnect

See [ADR 002 — single container client](../../../docs/architecture/decisions/002-single-container-client.md).

## Build

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --file build/docker/aqp_client/Dockerfile \
  --tag ghcr.io/julianwiley/aqp-client:dev \
  .
```

(build context is the AQP repo root)

## Local run

```bash
docker run --rm -it \
  -p 3000:8080 \
  -e AQP_CORE_API_URL=http://host.docker.internal:8000 \
  -e AQP_CONTROL_PLANE_URL=http://host.docker.internal:9000 \
  ghcr.io/julianwiley/aqp-client:dev
```
