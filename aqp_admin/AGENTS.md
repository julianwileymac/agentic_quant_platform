# AGENTS.md

Agent contract for `aqp_admin`.

## Purpose

Internal admin surface for AQP's managed services and company accounts.
Backend (FastAPI) and frontend (Vite + React) live side-by-side in this
folder. NOT a customer-facing admin and NOT a replacement for
`aqp_control_plane`.

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
5. **Never print or return raw tokens, kubeconfigs, or secret payloads.**
   See the always-on rule
   [.cursor/rules/aqp-management-engine.mdc](../.cursor/rules/aqp-management-engine.mdc).
6. **Frontend follows the same throttled-WS, kill-switch, sandbox-indicator,
   and typed-confirmation contracts as `aqp_client/`.** See
   [.cursor/rules/frontend.mdc](../.cursor/rules/frontend.mdc).

## Where Changes Go

| Change | Location |
| --- | --- |
| New `/admin/*` route | `src/aqp_admin/api/routers/` |
| New account flow | `src/aqp_admin/accounts/` |
| New managed-service action | `src/aqp_admin/services/` |
| New billing provider | `src/aqp_admin/providers/` |
| Shared type with AQP runtime | `../aqp_platform_core/src/aqp_platform_core/` |
| Frontend route | `aqp_admin_ui/src/routes/` |
| Typed API wrapper | `aqp_admin_ui/src/lib/api.ts` |
| Shared admin UI component | `aqp_admin_ui/src/components/` |

## Validation

```bash
# Backend
pip install -e ../aqp_platform_core
pip install -e .[dev]
pytest -ra
ruff check src tests
mypy src
rg --type py "^from aqp(\\.|$)|^import aqp(\\.|$)" src   # must return nothing

# Frontend
cd aqp_admin_ui
pnpm install
pnpm typecheck
pnpm test
pnpm build
```
