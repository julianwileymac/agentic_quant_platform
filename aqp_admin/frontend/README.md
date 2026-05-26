# AQP Admin Frontend (Next.js 15)

Next.js 15 App Router admin surface for AQP managed services + company
accounts. Replaces the Vite + React Router SPA in `aqp_admin_ui/`.

## Stack

- **Next.js 15** App Router, server components by default
- **React 19**, **TypeScript 5.9** strict
- **Tailwind v4** + shadcn-style component library (Radix primitives)
- **TanStack Query v5** for server state, **TanStack Table v8** for
  data grids
- **TipTap v2** for the runbook editor (lazy-loaded client component)
- **lightweight-charts** for OHLC + portfolio charts
- **openapi-typescript + openapi-fetch** for the typed API client
  (regenerated from the FastAPI `/openapi.json`)
- **Biome 1.9** for lint + format
- **Vitest 2** for unit + component tests

## Module surfaces

| Route | Purpose |
| --- | --- |
| `/dashboard` | Health overview |
| `/accounts` | Organizations |
| `/services` | Managed services lifecycle |
| `/settings` | Framework + cloud onboarding |
| `/terraform` | Terraform workspace runner |
| `/kubernetes` | Cluster status + pod list |
| `/tenants/new`, `/tenants/[orgId]` | Tenant vending wizard |
| `/builds`, `/builds/[id]` | Kaniko in-cluster builds |
| `/runbooks`, `/runbooks/[id]` | TipTap WYSIWYG runbooks |
| `/audit` | Audit ledger viewer |
| **`/secrets`** (NEW) | AWS Secrets Manager + ESO |
| **`/lineage/[urn]`** (NEW) | Bipartite lineage explorer |
| **`/models`** (NEW) | MLflow champion/challenger registry |
| **`/paper`** (NEW) | Paper-trading control |
| **`/rbac`** (NEW) | Role + Membership administration |
| **`/accounts/mode`** (NEW) | Single- vs multi-account switcher |

## Auth

Admin tokens validate via the existing
`@aqp/auth-client` workspace package (extracted from
`aqp_client/src/lib/auth/`). The `<AuthProvider>` wires either Auth0
SPA SDK or MSAL Browser depending on the runtime config returned by
`/admin/health`.

Step-up MFA per RFC 9470: every mutating call goes through
`apiFetch`, which auto-retries once on 401
`insufficient_user_authentication` after popping the IdP for fresh
MFA evidence (`useStepUp`).

## Kill switch

The topbar `<KillSwitch />` component fans out
`POST /admin/halt/all` (which targets every CP + monolith halt URL
in parallel). Friction-gated via `<ConfirmFrictionDialog />` — the
operator must type the word `halt` verbatim plus an optional reason
that lands in the audit ledger.

## WebSocket

`useChannel(name)` connects to `/admin/ws` (multiplexed) and
exposes the latest frame for a named channel:

```tsx
const lastFrame = useChannel("paper.task-abc123");
```

Channels are RBAC-namespaced — the backend rejects subscriptions to
`audit.tail` without `read:infrastructure` (or `admin:cluster`).

## Local dev

```bash
cd aqp_admin/frontend
pnpm install
pnpm openapi:generate     # backend must be running on :8900
pnpm dev                   # serves on http://localhost:3003
```

For backend-attached dev, set `AQP_ADMIN_API_URL=http://localhost:8900`
so the rewrites in `next.config.mjs` proxy `/admin/*` correctly.

## Validation

```bash
pnpm typecheck
pnpm lint
pnpm test
pnpm build
```

The CI matrix in `.github/workflows/aqp-admin.yml` runs all four.
