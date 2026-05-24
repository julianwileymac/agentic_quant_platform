# aqp-admin operator guide

> Read [../README.md](../README.md) for install. This page is the operator runbook.

## Surfaces

| Surface | Endpoint | Status |
| --- | --- | --- |
| Health | `GET /admin/health` | stub: returns `{status, version}` |
| Organizations list | `GET /admin/accounts/organizations` | stub returns `[]` |
| Billing summary | `GET /admin/accounts/billing/summary` | stub returns 501 |
| Tenancy invites | `GET /admin/accounts/tenancy/invites` | stub returns `[]` |
| Managed services | `GET /admin/services` | stub returns `[]` |
| Provision managed service | `POST /admin/services/{id}/provision` | stub returns 501 |
| Suspend managed service | `POST /admin/services/{id}/suspend` | stub returns 501 |

## Local boot

```bash
cd aqp_admin
pip install -e ../aqp_platform_core
pip install -e .[dev]
uvicorn aqp_admin.main:app --port 8900 --reload
# Open the SPA in a second terminal:
cd aqp_admin_ui
pnpm install && pnpm dev
```

## Auth model

`aqp_admin` enforces the same `IdentityProvider` chain as
[aqp_control_plane](../../aqp_control_plane/) (AQP rule 27). Internal
users sign in via the configured IdP; tokens are validated through the
shared provider; no vendor SDK call appears in route handlers.

Customer-account mutations cross-reference the ownership graph
(AGENTS rule 33) - every action that touches an Organization writes
a `resources` row + audit ledger entry.
