# aqp-index debt — Phase 3 cell topology

> Per the always-on
> [aqp-index-reflect rule](../rules/aqp-index-reflect.mdc), Phase 3
> §6 of
> [RESTRUCTURING_PLAN.md](../../RESTRUCTURING_PLAN.md) touches enough
> qualifying surfaces (Alembic migrations, persistence models,
> control-plane routes, ORM types, runtime context, a NEW subproject
> `aqp_tenant_router/`, multi-arch Dockerfile + K8s manifest trees,
> docs) that `aqp_index/` MUST be refreshed by the
> [`aqp-index-curator`](../agents/aqp-index-curator.md) subagent in
> the same PR — OR a debt note (this file) must capture the changed
> surfaces so the curator's next scheduled pass picks them up.
>
> This note is option 2. Invoke the curator before merging if at all
> possible.

## Surfaces changed in Phase 3

### `aqp_platform_core/`

- **`src/aqp_platform_core/topology/models.py`** — new
  `Cell`, `CellRoutes` Pydantic models + `CellTier`, `CellState`,
  `CellTenancyStrategy` literal aliases + `cells: list[Cell]`
  field on `DeploymentTopology`. New helpers
  `DeploymentTopology.cell_map`, `cells_for_tier(...)`,
  `active_cells()`. Mirrors the cells registry shape 1:1 with
  the Alembic `cells` table.
- **`src/aqp_platform_core/topology/__init__.py`** — re-exports
  the new symbols.
- **`src/aqp_platform_core/models/workloads.py`** — six new
  `WorkloadAction` enum values: `REGISTER_CELL`,
  `UPDATE_CELL_STATE`, `DRAIN_CELL`, `DECOMMISSION_CELL`,
  `PLACE_TENANT_IN_CELL`, `MIGRATE_TENANT_TO_CELL`.

### `alembic/`

- **`alembic/versions/0082_cell_registry.py`** (NEW) — creates
  `cells` + `cell_tenants` tables with CHECK constraints + the
  three secondary indexes (tier / region / state) and a UNIQUE
  index on `k8s_namespace`.
- **`alembic/versions/0083_audit_cell_id_column.py`** (NEW) —
  adds nullable `cell_id` FK columns to `security_audit_events`,
  `data_lineage_events`, `audit_log`. Replaces the
  `enforce_audit_log_hash_chain` Postgres function from Alembic
  `0079` (rule 6 respected — `0079` itself untouched) so the
  hash chain digest now includes `cell_id`. Backward-compatible:
  pre-Phase-3 rows hash to the same value because
  `coalesce(NULL, '') = ''`.
- **`alembic/versions/.hashes.lock`** — 2 new SHA-256 entries.

### `aqp/`

- **`aqp/persistence/models_cells.py`** (NEW) — SQLAlchemy ORM
  for the `cells` + `cell_tenants` tables. Carries the same
  CheckConstraints as the migration so bad inserts get rejected
  even when SQLAlchemy is bypassed.
- **`aqp/auth/context.py::RequestContext`** — three new fields:
  `cell_id`, `region`, `tenancy_strategy_alias`. `with_run_id`,
  `to_dict`, `to_finops_extras` all propagate the new fields.
- **`aqp/tenancy/strategies/shared_schema_rls.py::_set_session_context`** —
  now also issues `SET LOCAL app.current_cell_id` when the
  active `RequestContext` carries a `cell_id`. Adds the
  `_current_cell_id()` helper.
- **`aqp/api/middleware/tenancy_middleware.py`** — `TenancyContextMiddleware.dispatch`
  now stamps the active OTEL span with `aqp.cell.id`,
  `aqp.cell.region`, `aqp.tenancy.strategy`, `aqp.workspace.id`,
  `aqp.project.id` attributes via the new
  `_stamp_cell_span_attributes()` helper. Safe when OTEL is not
  installed.

### `aqp_control_plane/`

- **`src/aqp_cp/services/cells.py`** (NEW) — in-memory cell
  registry service that hydrates from `topology.yaml` and applies
  mutations. Hot path is pure-Python dict lookup; mutations
  audit-log through `WorkloadRuntime`. Will swap to SQLAlchemy
  in Phase 6 §9.1 when the control plane gets DB access.
- **`src/aqp_cp/api/routers/cells.py`** (NEW) — `/manage/cells/*`
  router: `GET /cells`, `GET /cells/{id}`, `POST /cells`,
  `PATCH /cells/{id}/state`, `DELETE /cells/{id}`,
  `GET /cells/{id}/tenants`, `POST /cells/{id}/tenants`,
  `POST /cells/{id}/tenants/{tenant_id}/migrate`,
  `POST /cells/reload`. Mutations route through
  `execute_with_audit` per AGENTS rule 45.
- **`src/aqp_cp/main.py::_setup_routers`** — registers the new
  `cells` router alongside the existing topology/tenants/builds/
  terraform set.

### `aqp_tenant_router/` (NEW SUBPROJECT)

- **`pyproject.toml`** — Hatch-based Python 3.11+ package with
  Starlette + uvicorn[standard] + python-jose + httpx + pydantic.
- **`AGENTS.md`** — boundary contract: HTTP-only, no aqp.* or
  aqp_cp.* imports, sub-millisecond hot path, Envoy ext_authz
  v3 compatibility.
- **`README.md`** — purpose + build + smoke-test commands.
- **`src/aqp_tenant_router/__init__.py`** — version stub.
- **`src/aqp_tenant_router/cache.py`** — `CellCache` +
  `CellEntry`. Thread-safe in-memory cell cache with periodic
  refresh against `/manage/cells`. Phase 5 §8.5 swap target.
- **`src/aqp_tenant_router/jwt_extract.py`** — `JwtClaims` +
  `extract_claims` + signature-aware `decode_and_validate`.
- **`src/aqp_tenant_router/main.py`** — Starlette app + 4 routes
  (`/healthz`, `/readyz`, `/resolve`, `/ext_authz/v3/check`) +
  CLI entrypoint (`aqp-tenant-router` console script).
- **`tests/test_resolve.py`** — six pytest smoke tests covering
  health/ready/resolve-pinned/resolve-fallback/ext_authz-anonymous/
  ext_authz-invalid-jwt.

### `aqp_platform/`

- **`aqp_platform/configs/deployment/topology.yaml`** — appended
  `cells:` bootstrap seed with four worked examples (local +
  three us-east-1 cells).
- **`aqp_platform/build/docker/aqp-edge/envoy.template.yaml`** —
  REPLACED the Phase 2 placeholder with a real cell-routing
  config (5 clusters: aqp_tenant_router + 4 per-cell upstreams,
  ext_authz filter, x-aqp-cell header match routes, 503 catch-all).
- **`aqp_platform/build/docker/aqp-tenant-router/Dockerfile`**
  (NEW) — Chainguard Wolfi multi-stage build per Phase 2 §5.1.
  UID 65532, uvloop + httptools entrypoint.
- **`aqp_platform/deployments/kubernetes/edge/aqp-edge/`** (NEW)
  — Deployment + Service + ServiceAccount + PDB + ConfigMap
  containing a working Envoy config.
- **`aqp_platform/deployments/kubernetes/edge/aqp-tenant-router/`**
  (NEW) — Deployment + Service + ServiceAccount + PDB. M2M
  token from the projected ServiceAccount volume.
- **`aqp_platform/deployments/kubernetes/edge/kustomization.yaml`**
  — added the two new subdirectories.
- **`aqp_platform/deployments/kubernetes/base-cell/kustomization.yaml`**
  (NEW) — cell-scoped base that omits cluster-wide namespaces +
  shared-infra aggregators. References files in sibling
  `../base/` (requires `--load-restrictor=LoadRestrictionsNone`).
- **`aqp_platform/deployments/kubernetes/cells/`** (NEW TREE)
  — three worked-example cell overlays:
  `shared-std-us-east-1a/`, `shared-prem-us-east-1a/`,
  `silo-reg-acme/`. Each ships kustomization.yaml +
  namespace.yaml with cell metadata labels, PSS restricted,
  FinOps quartet, and AQP_CELL_* env vars on aqp-core.
  Plus a top-level `README.md`.
- **`aqp_platform/deployments/argocd/applicationsets/cells-appset.yaml`**
  (NEW) — Argo CD ApplicationSet that stamps one Application
  per cell overlay directory. Sets
  `--load-restrictor=LoadRestrictionsNone` in
  `spec.source.kustomize.options`.

### `aqp_docs/`

- **`aqp_docs/docs/how-to/cell-router-cutover.md`** (NEW) —
  Phase 3 §6.4 cutover runbook covering the 5-week canary
  (10% → 50% → 100% → 7-day soak → proxy removal) with
  rollback steps for each phase.

## Files the curator should refresh

| `aqp_index/` file | Why it needs a refresh |
| --- | --- |
| `aqp_index/projects/aqp_platform_core.md` | New `Cell` / `CellRoutes` Pydantic models + `WorkloadAction` enum extension |
| `aqp_index/projects/aqp_control_plane.md` | New `/manage/cells/*` routes + `cells` service |
| `aqp_index/projects/aqp.md` | RequestContext fields; tenancy strategy GUC extension; new ORM model |
| `aqp_index/projects/aqp_tenant_router.md` (NEW FILE) | Entire new subproject |
| `aqp_index/projects/aqp_platform.md` | New aqp-edge config + aqp-tenant-router Dockerfile + cells/ K8s overlay tree |
| `aqp_index/projects/aqp_docs.md` | New cell-router-cutover.md runbook |
| `aqp_index/sources-of-truth.md` | Cells registry is the new SSoT for cell topology; cell_id is the new audit-row dimension |
| `aqp_index/config-sets/alembic.md` | Alembic head now `0083_audit_cell_id_column` |
| `aqp_index/config-sets/topology.md` | `cells:` section added to topology.yaml |
| `aqp_index/registries/subagents.md` | (No change unless we add a cell-router subagent) |

## Phase 3 §6 sub-section coverage

| RESTRUCTURING_PLAN.md sub-§ | Status |
| --- | --- |
| §6.1 — tier→strategy mapping | Encoded in the `_VALID_TIER_TO_STRATEGY` table inside `aqp_platform_core/topology/models.py` + the `Cell._validate_tier_strategy` validator |
| §6.2 — cell registry | Pydantic + Alembic 0082 + ORM + cells service + /manage/cells/* — complete |
| §6.3 — cell-aware RequestContext | RequestContext fields + SET LOCAL GUC + OTEL span attributes + Alembic 0083 audit cell_id columns — complete |
| §6.4 — Envoy cell router + tenant-router | Envoy config + aqp_tenant_router subproject + Dockerfile + K8s manifests — complete |
| §6.5 — per-cell K8s manifest overlay | base-cell + 3 worked-example cell overlays + Argo CD ApplicationSet — complete |
| §6.6 — REMOVE Python FastAPI proxy | DEFERRED to follow-up PR per the plan's "week 10" guidance |

## Follow-ups (Phase 3.5 / Phase 4+)

1. **Python proxy removal** (Phase 3 §6.6) — after the 7-day soak
   following the 100% canary; documented in the cutover runbook.
2. **Argo CD `aqp` AppProject** — the ApplicationSet references
   `project: aqp`; if that project doesn't exist, create it via
   the existing `aqp_platform/deployments/argocd/projects/`
   tree (not in Phase 3 scope).
3. **Per-cell datastores** (Phase 6 §9.1) — the current cell
   overlays inherit the shared `aqp` namespace's Postgres +
   Redis + MinIO. Phase 6 swaps these for per-cell CNPG +
   Redis + MinIO via additions to `base-cell/kustomization.yaml`.
4. **Cell-router CI image build** — add `aqp-edge` and
   `aqp-tenant-router` to `.github/workflows/build-multi-arch.yml`'s
   image matrix (currently only api/worker/client; tracked as a
   small follow-up under
   `.cursor/plans/aqp-index-debt-phase-2-supply-chain.md`).
5. **Tenant-router SPIFFE identity** (Phase 4 §7.2) — replace
   the M2M ServiceAccount token bootstrap with SPIRE-issued
   workload identity.
6. **Cell-Bound-Authorization (CBA)** (Phase 5 §8.5) — extend
   the tenant-router to validate biscuit capability tokens
   against the cell id.

## Provenance

- Discovered while implementing
  [RESTRUCTURING_PLAN.md](../../RESTRUCTURING_PLAN.md) Phase 3 in
  the same PR.
- All surfaces enumerated above show up in `git status` for
  this PR.
