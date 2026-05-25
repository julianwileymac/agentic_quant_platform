# AGENTS.md

Agent contract for `aqp_ui`.

## Purpose

`aqp_ui/` is the **cloud-hosted, customer-facing** Next.js 14+ App Router
application that bifurcates into:

- A public marketing site (SSR) at `aqp.fund`, `www.aqp.fund`, `/pricing`,
  `/docs/...`, `/legal/...`, `/about`, `/blog`, `/changelog`.
- An authentication-gated, multi-tenant operator dashboard at
  `app.aqp.fund` and `/dashboard`, `/strategies`, `/paper-runs`,
  `/backtests`, `/data`, `/ml`, `/agents`, `/workflows`, `/labs`,
  `/analytics`, `/research`, `/portfolio`, `/settings`.

It serves both B2B customers (enterprise SSO via Microsoft Entra ID
brokered through the existing `EntraTenantLink` flow) and B2C customers
(self-signup via Auth0 Organizations).

`aqp_ui` is intentionally separate from:

- [aqp_client/](../aqp_client/) — the Vite SPA for **local power users**.
- [aqp_admin/](../aqp_admin/) — the **internal admin** for AQP staff at
  `manage.aqp.fund`.
- [aqp_control_plane/](../aqp_control_plane/) — the workload lifecycle
  control plane consumed by all three frontends.

`aqp_ui` calls **into** the control plane and AQP API; it never replaces
them.

## Hard Boundaries

1. **Never import `aqp.*` or `aqp_control_plane.*`** anywhere in `src/`.
   HTTP-only access to the AQP monolith (`AQP_API_BASE`) and the control
   plane (`AQP_CONTROL_PLANE_URL`). Types come from the generated OpenAPI
   schema in `src/lib/api/generated/` (run `pnpm gen:api`).
2. **Identity flows through the existing `IdentityProvider` chain**
   (AQP rule 27). `aqp_ui` mints PKCE state, holds an httpOnly JWE
   session cookie, and forwards the access token via
   `Authorization: Bearer`. The backend validates with the existing
   `auth0-fastapi-api` + `MsalEntraProvider` validators. NEVER call vendor
   SDKs from a route handler that isn't under `src/app/api/auth/*`.
3. **Credentials resolve through the existing `CredentialResolver` chain**
   (AQP rule 26). The Next.js runtime reads `AUTH0_*` and `ENTRA_*` from
   environment-only env vars synced by External Secrets Operator from
   HashiCorp Vault. Never embed secrets in client bundles.
4. **Never print, log, or return raw tokens, kubeconfigs, or secret
   payloads** anywhere — see the always-on rule
   [.cursor/rules/aqp-management-engine.mdc](../.cursor/rules/aqp-management-engine.mdc).
   BFF route handlers MAY accept plaintext secrets ONCE on create (e.g.
   broker BYOK), encrypt in memory, drop the plaintext, never return it.
5. **Multi-tenancy contract.** Every `/api/*` handler reads the unified
   session via `getSession()` in [src/lib/auth/session.ts](src/lib/auth/session.ts),
   extracts the active `org_id` / `workspace_id` / `project_id` / `lab_id`
   / `mode` from JWT claims, and attaches them as `X-AQP-Org` /
   `X-AQP-Workspace` / `X-AQP-Project` / `X-AQP-Lab` / `X-AQP-Mode` HTTP
   headers via [src/lib/api/tenancy.ts](src/lib/api/tenancy.ts). Mirrors
   the contract already enforced in
   [aqp_client/src/lib/api/client.ts](../aqp_client/src/lib/api/client.ts).
6. **Step-up MFA (RFC 9470).** Every BFF handler that proxies a
   step-up-gated upstream endpoint (kill switch, broker BYOK CRUD,
   invite create/revoke, IdP connection CRUD, tenancy strategy
   migration, terraform apply/destroy) MUST bubble the
   `WWW-Authenticate: Bearer error="insufficient_user_authentication"`
   header back to the client unchanged. The client retries through
   [src/hooks/useStepUp.ts](src/hooks/useStepUp.ts).
7. **Kill-switch fan-out preserved.** `POST /api/kill-switch` MUST fan
   out via `Promise.allSettled` to every halt endpoint
   (`/portfolio/kill_switch`, `/agents/halt`, `/paper/stop-all`,
   `/bots/halt-all`, `/rl/halt-all`, `/workflows/halt`). Match the
   existing fan-out in
   [aqp_client/src/components/common/KillSwitch.tsx](../aqp_client/src/components/common/KillSwitch.tsx).
8. **EntityPicker for every name/credential selection.** Free-text inputs
   are reserved for descriptions, queries, and search boxes — never for
   the names of datasets, namespaces, sink kinds, Airbyte connectors,
   projects, credentials, broker credentials. Use
   [src/components/common/EntityPicker.tsx](src/components/common/EntityPicker.tsx)
   bound to the existing `/cache/{category}` upstream endpoint.
9. **WebSocket frame shape.** All WS frames preserve
   `{task_id, stage, message, timestamp, **extras}`. Match the canonical
   `aqp/tasks/_progress.py` contract. Do not rename keys.
10. **No backend business logic on the client.** API contracts live
    upstream in `aqp/api/routes/` and `aqp_control_plane/`; `aqp_ui`
    handlers are thin proxies that authenticate, attach tenancy headers,
    and forward bodies.
11. **CVE-2025-29927 pinning.** Next.js MUST be pinned to a patched line
    (`>=14.2.25`, `>=13.5.9`, `>=12.3.5`, or `>=15.2.3`). NEVER rely
    solely on `middleware.ts` for auth — every route handler MUST
    re-check the session.

## Where Changes Go

| Change | Location |
| --- | --- |
| Marketing page | `src/app/(marketing)/<slug>/page.tsx` |
| Auth screen | `src/app/(auth)/<slug>/page.tsx` |
| Protected dashboard page | `src/app/(app)/<slug>/page.tsx` |
| BFF route handler | `src/app/api/<area>/route.ts` |
| Auth0 SDK wiring | `src/lib/auth/auth0.ts` |
| Entra MSAL Node wiring | `src/lib/auth/entra.ts` |
| Unified session interface | `src/lib/auth/session.ts` |
| Typed HTTP client | `src/lib/api/client.ts` |
| Tenancy header builder | `src/lib/api/tenancy.ts` |
| WebSocket URL builder | `src/lib/ws/url.ts` |
| Shared UI primitive | `src/components/common/` |
| Marketing component | `src/components/marketing/` |
| Dashboard shell component | `src/components/shell/` |
| Auth flow component | `src/components/auth/` |
| Client hook | `src/hooks/` |
| Zustand store | `src/stores/` |
| Theme tokens | `src/providers/AntdProvider.tsx` |
| Generated OpenAPI types | `src/lib/api/generated/schema.d.ts` (codegen) |

## Validation

```bash
cd aqp_ui
pnpm install --frozen-lockfile
pnpm typecheck
pnpm lint
pnpm test
pnpm build

# Boundary guard: must return nothing.
rg --type ts --type tsx "from ['\"]@aqp/" src
rg --type ts --type tsx "from ['\"]\.\./\.\./aqp" src

# CVE-2025-29927 guard: never trust middleware alone.
rg --type ts "auth0\.getSession" src/app/api  # every handler should call it
```

## See Also

- [README.md](README.md) — Dev quickstart and env matrix.
- [aqp_docs/docs/concepts/identity/identity.md](../aqp_docs/docs/concepts/identity/identity.md) — Existing `IdentityProvider`
  chain, Auth0 / Entra / OIDC / Cloudflare Access providers.
- [aqp_docs/docs/concepts/identity/multi-tenancy.md](../aqp_docs/docs/concepts/identity/multi-tenancy.md) —
  Four `TenancyStrategy` implementations (RLS / schema-per-tenant /
  db-per-enterprise / hybrid).
- [aqp_docs/docs/concepts/identity/account-management.md](../aqp_docs/docs/concepts/identity/account-management.md) —
  Auth0 Management API client, `EntraTenantLink`, invites.
- [.cursor/rules/aqp-ui.mdc](../.cursor/rules/aqp-ui.mdc) — Glob-scoped
  enforcement of this contract.
- [.cursor/rules/frontend.mdc](../.cursor/rules/frontend.mdc) — Throttled
  WS, kill-switch fan-out, sandbox indicator (shared with `aqp_client`
  and `aqp_admin_ui`).
