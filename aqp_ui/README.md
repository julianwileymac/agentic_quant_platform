# aqp-ui

Cloud-hosted, multi-tenant Platform-as-a-Service frontend for the
Agentic Quant Platform. Serves both B2C self-signup customers (via Auth0
Organizations) and B2B enterprise tenants (via Microsoft Entra ID
brokered through the existing `EntraTenantLink` flow).

## Scope

This package is the **customer-facing** cloud UI:

- **Public marketing site** (SSR for SEO) at `aqp.fund` and `www.aqp.fund`
  — homepage, pricing, docs, legal, about, blog, changelog.
- **Auth screens** at `/signup`, `/login`, `/onboarding/*` —
  provider-aware (Auth0 for B2C, Entra for B2B).
- **Authenticated operator dashboard** at `app.aqp.fund` and `/dashboard`,
  `/strategies`, `/paper-runs`, `/backtests`, `/data`, `/ml`, `/agents`,
  `/workflows`, `/labs`, `/analytics`, `/research`, `/portfolio`,
  `/settings`.

`aqp_ui` is intentionally separate from:

- [aqp_client/](../aqp_client/) — the Vite operator UI for **local power
  users** (no public hostname).
- [aqp_admin/](../aqp_admin/) — the **internal admin** for AQP staff at
  `manage.aqp.fund`.
- [aqp_control_plane/](../aqp_control_plane/) — the per-workload control
  plane API.

`aqp_ui` calls **into** these services over HTTP and WebSocket; it never
replaces them.

## Stack

| Layer | Choice |
| --- | --- |
| Framework | Next.js 14+ App Router |
| Runtime | Node 20+ |
| UI library | Ant Design 5 (`@ant-design/nextjs-registry` for SSR style extraction) |
| Auth (B2C) | `@auth0/nextjs-auth0` v4 |
| Auth (B2B) | `@azure/msal-node` confidential client |
| State (server) | TanStack Query v5 |
| State (client) | Zustand v5 |
| Forms (schema-driven) | `@rjsf/antd` + `@rjsf/validator-ajv8` |
| YAML round-trip | `yaml` |
| Lint / format | Biome 1.x |
| Tests (unit) | Vitest 2.x + `@testing-library/react` |
| Tests (e2e) | Playwright |
| Build | `output: 'standalone'` for slim Docker image |
| Package manager | pnpm 9.x |

## Layout

```
aqp_ui/
├── AGENTS.md                 # Boundary contract
├── README.md                 # This file
├── package.json
├── next.config.mjs
├── tsconfig.json
├── biome.json
├── middleware.ts             # Auth0 + Entra session gate
├── postcss.config.mjs        # Tailwind 4 PostCSS plugin
├── vitest.config.ts
├── playwright.config.ts
├── public/                   # Static assets
├── src/
│   ├── app/                  # App Router
│   │   ├── layout.tsx        # Root + AntdRegistry + providers
│   │   ├── globals.css
│   │   ├── not-found.tsx
│   │   ├── (marketing)/      # Public, SSR
│   │   ├── (auth)/           # Auth screens
│   │   ├── (app)/            # Protected dashboard
│   │   └── api/              # BFF route handlers
│   ├── lib/
│   │   ├── auth/             # auth0, entra, session, tenant, stepUp
│   │   ├── api/              # client, tenancy, generated
│   │   ├── ws/               # WebSocket URL builder
│   │   └── cn.ts             # clsx + tailwind-merge
│   ├── providers/            # Antd, Query, AuthClient
│   ├── components/           # marketing, shell, auth, strategy, telemetry, common
│   ├── hooks/                # useCeleryTask, useMarketStream, useStepUp, useAuth
│   └── stores/               # ui, tenancy, telemetry, market
├── tests/
│   ├── setup.ts
│   ├── smoke.test.tsx
│   └── e2e/                  # Playwright specs
└── .env.example
```

## Dev quickstart

```bash
cd aqp_ui
pnpm install

# Configure auth (copy .env.example to .env.local and fill in values)
cp .env.example .env.local

# Start the Next.js dev server (port 3002 to avoid clashing with
# aqp_client at 3001 and aqp_admin_ui at 3003)
pnpm dev

# In another shell: keep the AQP backend running on :8000
docker compose up -d aqp-api
```

Open `http://localhost:3002` for the marketing site and
`http://localhost:3002/dashboard` for the (auth-gated) dashboard.

## Environment variables

See [.env.example](.env.example). The minimum required set:

```
# App
AQP_UI_PORT=3002
AQP_UI_BASE_URL=http://localhost:3002

# Upstream
AQP_API_BASE=http://localhost:8000
AQP_CONTROL_PLANE_URL=http://localhost:8800
AQP_WS_URL=ws://localhost:8000

# Auth0 (B2C self-signup)
AUTH0_DOMAIN=aqp-fund.us.auth0.com
AUTH0_CLIENT_ID=...
AUTH0_CLIENT_SECRET=...
AUTH0_AUDIENCE=https://api.aqp.internal
AUTH0_SECRET=<generate via `openssl rand -hex 32`>

# Entra (B2B enterprise SSO)
ENTRA_TENANT_ID=common              # multi-tenant
ENTRA_CLIENT_ID=...
ENTRA_CLIENT_SECRET=...
ENTRA_REDIRECT_URI=http://localhost:3002/api/auth/entra/callback

# Session encryption (separate from Auth0_SECRET; AES-256 key)
AQP_UI_SESSION_SECRET=<generate via `openssl rand -hex 32`>
```

## Scripts

```bash
pnpm dev               # Next.js dev server on :3002
pnpm build             # Production build (uses output: 'standalone')
pnpm start             # Run the production server
pnpm typecheck         # tsc --noEmit
pnpm lint              # Biome
pnpm format            # Biome --write
pnpm test              # Vitest run
pnpm test:watch        # Vitest watch
pnpm test:e2e          # Playwright
pnpm gen:api           # openapi-typescript ../data/openapi.json -o src/lib/api/generated/schema.d.ts
```

## Auth flows at a glance

### B2C self-signup (Auth0)

1. User clicks "Sign up" on the marketing site, lands at `/signup`.
2. Picks "Sign up with email" or social provider.
3. Auth0 Universal Login → callback at `/api/auth/callback`.
4. BFF writes the JWE session cookie, creates a new Auth0 Organization
   (one Org per tenant), and calls upstream
   `POST /tenancy/organizations` to materialize the matching
   `Organization` + `Workspace` + `Project` rows.
5. User lands at `/onboarding/org-create` for slug/name picking, then
   `/dashboard`.

### B2B enterprise SSO (Entra)

1. IT admin clicks "Sign in with Microsoft" on `/login`.
2. MSAL Node confidential-client flow against the customer's Entra
   tenant.
3. BFF gets `tid` from the id_token, queries upstream
   `GET /tenancy/entra-links?tid={tid}`.
4. If `active` link exists → use linked `Organization`, land on
   `/dashboard`.
5. If `pending` or absent → BFF creates the `pending` row, redirects to
   `/onboarding/entra-tenant-link` to wait for AQP super-admin approval.

Both flows write to the same unified JWE session cookie, so the
downstream `(app)/*` dashboard is identical for both customer types.

## Status

Active scaffold. Sprint 0 (skeleton + AGENTS.md + smoke test) complete.
Sprint 1 (dual auth) in progress. See [.cursor/plans/](../.cursor/plans/)
for sprint tracking.
