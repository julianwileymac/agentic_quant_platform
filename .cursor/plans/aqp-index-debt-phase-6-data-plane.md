# aqp_index debt — Phase 6 data plane silo per cell

Triggered by: `RESTRUCTURING_PLAN.md` §9 implementation
(per-cell data plane + cell-aware engine / Iceberg / Vault Transit).

## Surfaces that need a curator pass

The curator MUST refresh the `aqp_index/` pointers for the following
surfaces. Each entry lists the file the curator would update and the
new signature / pointer it should record.

### 1. `aqp_platform/deployments/helm/`

- **New chart**: `aqp-cell-data-plane/` (the per-cell data plane chart).
- **Template files** (one per Phase 6 §9 deliverable):
  - `Chart.yaml`, `values.yaml`, `templates/_helpers.tpl`
  - `templates/postgres-cnpg.yaml`
  - `templates/redis.yaml`
  - `templates/minio.yaml` (with Object Lock COMPLIANCE bootstrap Job)
  - `templates/mlflow.yaml`
  - `templates/iceberg-rest.yaml`
  - `templates/vault-secrets.yaml` (Phase 4 §7.6 VaultStaticSecret CRs)
- Curator should record the chart name + verified `helm template` count
  (15 objects rendered for `cell_id=cell-shared-std-us-east-1a`).

### 2. `aqp_platform_core/topology/models.py`

- **New model**: `CellDataPlane` (Phase 6 §9 — `postgres_dsn_secret`,
  `redis_url`, `minio_endpoint`, `minio_bucket_prefix`,
  `mlflow_tracking_uri`, `iceberg_rest_uri`, `iceberg_warehouse_uri`,
  `vault_transit_key`).
- **Modified**: `Cell` now carries `data_plane: CellDataPlane`.
- **Modified**: `ServiceDefinition.app_label` is now optional (with a
  `model_validator` that requires it for non-external workloads).
- Curator should refresh the signature index for these classes.

### 3. `aqp/deployment/topology.py`

- Now re-imports `Cell`, `CellDataPlane`, `CellRoutes`, `CellState`,
  `CellTenancyStrategy`, `CellTier` from `aqp_platform_core` so the two
  modules stay in lockstep.
- `DeploymentTopology` now carries `cells: list[Cell]` plus `cell_map`,
  `cells_for_tier`, `active_cells` accessors.
- `ServiceDefinition.app_label` is now optional + validator.

### 4. `aqp/data/iceberg_catalog.py`

- **New helpers**: `_cell_data_plane()`, `_active_cell_id()`.
- **Modified**: `_build_properties()` now consults the per-cell data
  plane.
- **Modified**: `get_catalog()` is now keyed by `cell_id`
  (via `_load_catalog_for_cell` LRU cache, maxsize 32).
- **Modified**: `reset_catalog_cache()` evicts every cell-keyed entry.

### 5. `aqp/credentials/vault_transit.py`

- **New helpers**: `_active_cell_transit_key()`,
  `_resolve_transit_key_name(tenant)`.
- **Modified**: `_vault_encrypt` and `_vault_decrypt` now use the
  per-cell transit key when bound to a `silo-reg`-style cell with a
  populated `data_plane.vault_transit_key`.

### 6. `aqp/persistence/db.py`

- Now built around `_sync_engine_for_cell(cell_id)` and
  `_async_engine_for_cell(cell_id)` LRU caches keyed by cell id.
- The legacy `_sync_engine()` / `_async_engine()` are now thin wrappers
  that resolve the active cell from the runtime context.
- New `reset_engine_cache()` helper for tests.
- `SessionLocal` and `AsyncSessionLocal` proxies are unchanged
  externally — they now resolve through the cell-keyed cache.

### 7. `aqp/tenancy/protocol.py`

- New `TenancyStrategy.get_engine(org_id)` /
  `get_async_engine(org_id)` methods with default implementations
  that delegate to the cell-keyed engine.
- `DatabasePerEnterpriseStrategy` overrides both to make the silo-reg
  cell binding explicit.

### 8. `aqp/config/settings.py`

- **New settings**: `cell_dual_write: bool` (AQP_CELL_DUAL_WRITE),
  `cell_default_id: str` (AQP_CELL_DEFAULT_ID).
- `.env.example` updated with the new env vars.

### 9. `aqp_platform/configs/deployment/topology.yaml`

- Three of the four existing cells now carry a populated `data_plane:`
  block (`cell-shared-std-us-east-1a`, `cell-shared-prem-us-east-1a`,
  `cell-silo-reg-acme`). The local dev cell stays without one (legacy
  shared data plane).

### 10. `scripts/cells/dual_write_backfill.py`

- **New script**: tenant-scoped backfill from the shared plane into a
  per-cell plane. Dry-run by default; `--apply` for the write path;
  `--reconcile-only` for parity verification.

### 11. `aqp_docs/docs/how-to/cell-data-plane-migration.md`

- **New runbook**: step-by-step migration of a tenant from the shared
  data plane into a per-cell silo.

### 12. `tests/test_iceberg_cell_aware.py`

- **New tests**: exercise `_cell_data_plane()`, `_active_cell_id()`,
  `_build_properties()` for every cell tier (local fallback,
  shared-std, shared-prem, silo-reg, unknown).

## Why a curator pass is needed

Phase 6 introduces a NEW dimension (cell) into existing AQP signatures.
Without an `aqp_index/` refresh, agents will continue to cite:

- the old `_build_properties()` signature (no cell awareness)
- the old `SessionLocal` resolution (single engine, not per-cell)
- the absence of `CellDataPlane` from the topology model surface
- the `Cell` model without its `data_plane` block

This index drift would compound across phases.

## Curator entry-point (when run)

```bash
# From the repo root.
codex run-agent aqp-index-curator \
  --reason "Phase 6 data plane silo per cell" \
  --surfaces "aqp_platform/deployments/helm/aqp-cell-data-plane,aqp_platform_core/topology/models.py,aqp/deployment/topology.py,aqp/data/iceberg_catalog.py,aqp/credentials/vault_transit.py,aqp/persistence/db.py,aqp/tenancy/protocol.py,aqp/config/settings.py,aqp_platform/configs/deployment/topology.yaml,scripts/cells/dual_write_backfill.py,aqp_docs/docs/how-to/cell-data-plane-migration.md,tests/test_iceberg_cell_aware.py"
```
