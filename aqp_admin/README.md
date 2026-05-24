# aqp-admin

Internal admin surface for AQP's **managed services** and **company accounts**.

## Scope

This package is the internal control surface for AQP's operations team — NOT
a customer-facing admin. It contains:

- **Company accounts** — organizations, billing, tenancy, internal-user
  lifecycle, identity-provider links.
- **Managed services** — orchestration of the SaaS catalog AQP offers to
  customers (provisioning, throttling, quotas, suspension, cost roll-up).

It is intentionally separate from:

- [aqp_control_plane/](../aqp_control_plane/) — the per-workload control
  plane (`/manage/*`) shared between embedded and sidecar deploys.
- [aqp_client/](../aqp_client/) — the customer-facing operator UI.

`aqp_admin` calls **into** the control plane and AQP API; it never replaces
them.

## Layout

```
aqp_admin/
├── src/aqp_admin/           # FastAPI backend (Python)
│   ├── main.py              # /admin/* app
│   ├── settings.py
│   ├── api/routers/         # accounts.py, services.py, health.py
│   ├── accounts/            # organizations, billing, tenancy
│   ├── services/            # managed-service catalog
│   └── providers/           # billing/payment providers (stripe, ...)
├── aqp_admin_ui/            # Vite 7 + React 19 + Tailwind 4 + shadcn frontend
│   ├── src/routes/          # dashboard, accounts, services
│   ├── src/components/      # shared admin UI
│   └── src/lib/api.ts       # typed httpx-style wrappers
├── tests/                   # pytest (backend) + vitest (frontend)
└── docs/
```

## Boundaries

- **No `import aqp.*`** in `src/aqp_admin/`. Shared value types come from
  [aqp_platform_core](../aqp_platform_core/). HTTP-only access to the
  AQP monolith and control plane.
- **No backend business logic in the frontend.** API contracts live in
  `src/aqp_admin/api/routers/`; the frontend calls them through
  `aqp_admin_ui/src/lib/api.ts`.
- **Credentials + identity** route through the same chain documented in
  [aqp_docs/credentials.md](../aqp_docs/credentials.md) and
  [aqp_docs/identity.md](../aqp_docs/identity.md). No vendor SDK calls
  from route handlers.
- **Audit-first**: every mutating route writes a structured audit record
  before performing the action. Failure modes never leave the audit ledger
  out of sync with reality.

## Backend dev

```bash
cd aqp_admin
pip install -e ../aqp_platform_core
pip install -e .[dev]
pytest -ra
uvicorn aqp_admin.main:app --port 8900
```

## Frontend dev

```bash
cd aqp_admin/aqp_admin_ui
pnpm install
pnpm dev          # http://localhost:3003
pnpm typecheck
pnpm test
pnpm build
```

## Status

Skeleton only. See [docs/architecture.md](docs/architecture.md) for the
target shape and [docs/index.md](docs/index.md) for the operator runbook.
