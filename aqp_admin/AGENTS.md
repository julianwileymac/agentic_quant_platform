# AGENTS.md

Agent contract for `aqp_admin`.

## Purpose

Internal admin surface for AQP's managed services and company accounts.
Backend (FastAPI 0.118+ async) and frontend (Next.js 15 App Router)
live side-by-side in this folder. NOT a customer-facing admin and NOT
a replacement for `aqp_control_plane`.

The Vite + React Router SPA in `aqp_admin_ui/` is the legacy frontend.
It remains deployable behind a feature flag for a 30-day rollback
window during the Next.js cutover; new development goes into
`aqp_admin/frontend/` only.

## Hard Boundaries

1. **Never import `aqp.*`** in `src/aqp_admin/`. Shared value types come
   from [aqp_platform_core](../aqp_platform_core/). HTTP-only access to
   the AQP monolith and control plane.
2. **Audit-first.** Every mutating route writes a structured audit record
   BEFORE performing the action. Mirrors the `workload_runs` pattern in
   [aqp_platform_core/runtime/workload.py](../aqp_platform_core/src/aqp_platform_core/runtime/workload.py).
3. **Identity flows through `IdentityProvider`** (AQP rule 27). Never call
   vendor SDKs (Auth0, MSAL) directly from route handlers.
4. **Credentials resolve through `CredentialResolver`** (AQP rule 26). Never
   read `settings.*_secret` directly in route handlers.
5. **Step-up MFA on every destructive admin route** per AGENTS rule 52.
   Use `aqp_admin.deps.stepup.require_admin_step_up(*scopes)`. The
   Phase 2 allowlist debt for `aqp_admin/halt.py` is closed.
6. **Never print or return raw tokens, kubeconfigs, or secret payloads.**
   See the always-on rule
   [.cursor/rules/aqp-management-engine.mdc](../.cursor/rules/aqp-management-engine.mdc).
7. **Frontend follows the same throttled-WS, kill-switch, sandbox-indicator,
   and typed-confirmation contracts as `aqp_client/`.** See
   [.cursor/rules/frontend.mdc](../.cursor/rules/frontend.mdc).
8. **NO Casbin.** The RBAC admin module wraps the canonical 4-role
   lattice in `aqp_platform_core.auth.rbac` plus the existing
   `Membership` table. Adding a parallel policy engine breaks rule 27.

## Where Changes Go

| Change | Location |
| --- | --- |
| New `/admin/*` route | `src/aqp_admin/api/routers/` |
| New account flow | `src/aqp_admin/accounts/` |
| New managed-service action | `src/aqp_admin/services/` |
| New billing provider | `src/aqp_admin/providers/` |
| New broker method (e.g. data MCP, MLflow) | `src/aqp_admin/integrations/broker.py` |
| New WebSocket channel | `src/aqp_admin/ws/gateway.py` `_CHANNEL_REQUIRED_SCOPES` |
| Step-up gate | `src/aqp_admin/deps/stepup.py::require_admin_step_up` |
| Shared type with AQP runtime | `../aqp_platform_core/src/aqp_platform_core/` |
| Frontend route | `frontend/app/(admin)/<name>/page.tsx` |
| Typed API wrapper | regenerated into `frontend/lib/api/generated/` via `pnpm openapi:generate` |
| Shared admin UI component | `frontend/components/` |

## Validation

```bash
# Backend
pip install -e ../aqp_platform_core
pip install -e .[dev]
pytest -ra
ruff check src tests
mypy src
rg --type py "^from aqp(\\.|$)|^import aqp(\\.|$)" src   # must return nothing

# Frontend (canonical Next.js 15 surface)
cd frontend
pnpm install
pnpm typecheck
pnpm lint
pnpm test
pnpm build

# Frontend (legacy Vite — only when running the rollback feature flag)
cd ../aqp_admin_ui
pnpm install
pnpm typecheck
pnpm test
pnpm build
```
