# `management/frontend/` — DEPRECATED (Phase 7)

> **Status**: Sunset. The AQP refactor folds operator UI into the unified `aqp_client` container.

## Why

The AQP refactor consolidates every operator surface into the unified
`aqp_client` container (see
`agentic_quant_platform/docs/architecture/decisions/002-single-container-client.md`
in the sibling AQP repository):

- Single image, single port (`:8080`)
- Vite SPA at `/`
- Legacy Solara UI at `/legacy`
- `/api/*`, `/ml/*`, `/mcp/*`, `/manage/*` reverse-proxied to the relevant backend
- One Auth0 tenant + one Cloudflare Tunnel ingress

Maintaining a parallel Next.js operator UI in `rpi_kubernetes/management/frontend/` duplicates auth wiring, nav structure, and the cluster-ops view.

## Migration plan

| Page here                | New home in `aqp_client`                  | Status      |
| ------------------------ | ------------------------------------------ | ----------- |
| `/nodes`                 | AQP Vite `/cluster-mgmt` / `aqp cp cluster pods` | Compatibility only |
| `/deployments`           | `frontend/src/routes/control-plane/deployments/page.tsx` | Mature |
| `/services`              | AQP Vite `/manage` / `aqp cp deployments list` | Compatibility only |
| `/hardware`              | `frontend/src/routes/analytics/...`        | Pending     |
| `/monitoring`            | `frontend/src/routes/analytics/...`        | Pending     |
| `/mlflow`                | `frontend/src/routes/ml/...` (existing)    | Mature      |
| `/docs`                  | Static asset on `aqp_client`               | Pending     |
| `/settings`              | `frontend/src/routes/control-plane/...`    | Pending     |

## What to do today

- **No new pages here.** Add them to `agentic_quant_platform/frontend/src/routes/`.
- **No new API integrations here.** The control plane's `/manage/*`
  endpoints are reachable from the AQP frontend via `aqp_client`, and
  from the CLI via `aqp cp ...`.
- **Auth migration.** This frontend currently uses `@auth0/auth0-react` against the rpi-management Auth0 app. The AQP frontend uses the same tenant but a different SPA app (`aqp-client`). Migration replaces the Auth0 SDK call sites with the existing `useAuth()` hook in `frontend/src/lib/auth/useAuth.ts`.

## Removal timeline

Same as `management/backend/DEPRECATED.md`:

- **Now**: deprecation banner (this file)
- **Next release**: nav items in the Next.js shell carry a yellow "moved to AQP" badge
- **Following release**: pages 301-redirect to the new AQP routes
- **After 90 days**: deletion
