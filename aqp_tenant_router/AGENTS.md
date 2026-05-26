# AGENTS.md

Agent contract for `aqp_tenant_router`.

## Purpose

`aqp_tenant_router` is the cell-routing decision service for the
Agentic Quant Platform. It resolves a JWT (`sub`, `workspace_id`,
optional `tenant_id`) to a cell identity (`cell_id`, `region`,
`k8s_namespace`, `routes`) on the hot path between Envoy
(`aqp-edge`) and the per-cell FastAPI instances.

The router is the Phase 3 §6.4 (RESTRUCTURING_PLAN.md) deliverable
for the "cell router (Envoy) replaces single-container client"
work item.

Two consumers:

- **Envoy `ext_authz` filter** at `aqp-edge` calls
  `POST /ext_authz/v3/check` for every inbound request. The
  response either approves the request and injects an
  `x-aqp-cell: <cell_id>` header, or denies with a `503`-style
  body when no cell can serve the tenant.
- **Direct callers** (the `aqp-cli` cell admin commands, the
  `aqp_admin` cell dashboard) call `POST /resolve` to look up a
  tenant's cell without going through Envoy.

## Hard Boundaries

1. **No `import aqp.*` or `import aqp_cp.*`.** The router speaks HTTP
   only. It calls the control plane's `/manage/cells/*` routes for
   the cell registry, the AQP main API's `/auth/userinfo` for JWT
   validation (or validates the JWT locally against the Auth0 / Entra
   JWKS). It must not pull the AQP runtime into its image.
2. **Sub-millisecond hot path.** The router caches cell metadata in
   memory with a periodic refresh (default 30s). A cache miss falls
   back to a single call to `/manage/cells/{cell_id}` but never
   triggers a full re-fetch on the request thread.
3. **JWT is read-only.** The router never signs or modifies tokens.
   It extracts `sub` + claims, optionally validates against JWKS,
   and routes. Token re-issuance is the AQP main API's job.
4. **Single language.** Pure Python + Starlette + uvloop +
   httptools (chosen explicitly per the Phase 3 scoping question).
   Do not add Go, Rust, or C extensions without a separate scoping
   discussion — the goal is to keep the toolchain Python-only.
5. **`/ext_authz/v3/check` MUST stay compatible with Envoy's
   external authorization HTTP protocol** (v3 contract). Changes
   to the response envelope require both an integration test
   against an Envoy instance AND a follow-up note in the
   `aqp-edge` Envoy config at
   `aqp_platform/build/docker/aqp-edge/envoy.template.yaml`.

## Where Changes Go

- New route: `src/aqp_tenant_router/main.py`.
- New cache backend (Redis-cached cell registry, future
  Phase 5 work): `src/aqp_tenant_router/cache.py`.
- JWT extraction / validation: `src/aqp_tenant_router/jwt_extract.py`.
- Tests: `tests/` mirroring the source layout.
- New Dockerfile (Chainguard Wolfi per Phase 2 §5.1):
  `../aqp_platform/build/docker/aqp-tenant-router/Dockerfile`.
- K8s manifests:
  `../aqp_platform/deployments/kubernetes/edge/aqp-tenant-router/`.

## Configuration

The router takes configuration from environment variables, all
namespaced `AQP_TENANT_ROUTER_*`:

- `AQP_TENANT_ROUTER_CONTROL_PLANE_URL` — base URL of the AQP
  control plane (default `http://aqp-cp.aqp-admin.svc.cluster.local:9000`).
- `AQP_TENANT_ROUTER_AUTH0_DOMAIN` — JWKS host for JWT signature
  verification.
- `AQP_TENANT_ROUTER_REFRESH_INTERVAL_SECONDS` — cell-cache refresh
  interval (default `30`).
- `AQP_TENANT_ROUTER_M2M_TOKEN_FILE` — path to a ServiceAccount
  token used to authenticate to the control plane. Phase 4 §7.2
  will replace this with SPIFFE identity once SPIRE lands.

## Validation

```bash
pip install -e .[dev]
pytest -ra
ruff check src tests
```

## Phase notes

Phase 3 ships the in-memory cache + the canonical resolve API +
the Envoy ext_authz adapter. Phase 5 §8.5 adds Cell-Bound-
Authorization (CBA) validation; Phase 4 §7.2 replaces the M2M
token bootstrap with SPIFFE workload identity.
