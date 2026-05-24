# aqp_client

Status: active client package.

`aqp_client` is the local AQP client experience: Vite 7, React 19,
TypeScript 5.9, Tailwind CSS 4, shadcn/ui, API wrappers, WebSocket
wrappers, visualization routes, and operator workflows.

## Owns

- Operator UI architecture and client-side workflows.
- Generated API contracts and typed client guidance.
- Local session, cache, activity, and alert subscription conventions.
- Client gateway expectations for `/api/*`, `/mcp/*`, `/manage/*`, and
  WebSocket streams.

## Structure

| Responsibility | Path |
| --- | --- |
| Vite source | `src/` |
| Unit/e2e tests | `tests/` |
| Static assets | `public/` |
| Docker image | `Dockerfile` |
| API wrappers | `src/lib/api/` |
| WebSocket wrappers | `src/lib/ws/` |
| Deployment manifests | `../aqp_platform/deployments/kubernetes/base/aqp-client` |
| Legacy rollback UI | `../webui` |

## Quick Start

```bash
pnpm --dir aqp_client install
pnpm --dir aqp_client dev
pnpm --dir aqp_client typecheck
pnpm --dir aqp_client test
pnpm --dir aqp_client build
```

## Boundary Rules

- All HTTP access goes through `src/lib/api/`.
- All WebSocket access goes through `src/lib/ws/`.
- Consequential actions use `ConfirmFrictionDialog`.
- Backend business logic stays in `../aqp/` or `../aqp_control_plane/`.
  The client consumes typed contracts and gateway routes.

