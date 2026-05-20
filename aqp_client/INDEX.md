# aqp_client Index

## Live Implementation

- Vite app: `src/`
- Client API wrappers: `src/lib/api`
- WebSocket wrappers: `src/lib/ws`
- Client deployment: `../deployments/kubernetes/base/aqp-client`
- Client Dockerfile: `../aqp_client/Dockerfile`
- Legacy rollback UI: `../webui`

## Contracts To Preserve

- API calls flow through typed wrappers and generated OpenAPI types.
- Kill-switch fan-out stays aligned with backend halt endpoints.
- WebSocket frames keep the canonical task progress shape.
- Consequential actions use typed confirmation friction.

## Compatibility Notes

The old `../frontend` path is now a temporary compatibility stub for ignored
local build/cache files. Do not add active source there.

