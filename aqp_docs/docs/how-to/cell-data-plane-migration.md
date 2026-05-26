# Cell data plane migration runbook

Phase 6 §9 (`RESTRUCTURING_PLAN.md`) — operating procedure for
provisioning a per-cell data plane and migrating a tenant from the
shared cluster-wide Postgres/Redis/MinIO/MLflow/Iceberg into the
dedicated cell.

This runbook is the canonical companion to:

| Surface | Path |
| --- | --- |
| Helm chart | `aqp_platform/deployments/helm/aqp-cell-data-plane/` |
| Topology models | `aqp_platform_core/src/aqp_platform_core/topology/models.py` |
| Cell registry seed | `aqp_platform/configs/deployment/topology.yaml` |
| Dual-write switch | `AQP_CELL_DUAL_WRITE` (`aqp/config/settings.py`) |
| Backfill script | `scripts/cells/dual_write_backfill.py` |
| Iceberg cell-awareness | `aqp/data/iceberg_catalog.py:_cell_data_plane` |
| Vault Transit cell-key | `aqp/credentials/vault_transit.py:_resolve_transit_key_name` |
| Engine cell-keying | `aqp/persistence/db.py:_sync_engine_for_cell` |

## When to use this runbook

You SHOULD migrate a tenant into a dedicated per-cell data plane when:

- A regulatory commitment requires cryptographic data-plane separation
  (FINRA, ISO 27001, SOC 2 with customer-side isolation).
- The tenant signs onto a `silo-reg` or `silo-custom` contract.
- A multi-AZ blast-radius failure isolated to one cell should not
  affect other tenants.

You SHOULD NOT use this runbook for:

- A `shared-std` cell — those share the cluster-wide data plane by
  design.
- An ordinary regional cutover (use `cell-router-cutover.md` instead).

## Pre-flight

1. **Cell exists in `topology.yaml`.** Verify the destination cell id
   in the `cells:` section with a populated `data_plane:` block:
   ```yaml
   - id: cell-silo-reg-acme
     tier: silo-reg
     tenancy_strategy: database_per_enterprise
     # ...
     data_plane:
       postgres_dsn_secret: secret/aqp/cells/cell-silo-reg-acme/postgres
       iceberg_rest_uri: http://aqp-cell-iceberg-rest.cell-silo-reg-acme.svc.cluster.local:8181
       iceberg_warehouse_uri: s3://aqp-cell-silo-reg-acme-warehouse/
       minio_endpoint: http://aqp-cell-minio.cell-silo-reg-acme.svc.cluster.local:9000
       vault_transit_key: aqp-cell-silo-reg-acme
   ```
   The `vault_transit_key` is **mandatory** for `silo-reg` cells.

2. **Vault paths exist.** Seed every credential the chart consumes:
   - `secret/aqp/cells/<cell>/postgres` — `username` + `password`
   - `secret/aqp/cells/<cell>/minio` — `access_key` + `secret_key`
   - `secret/aqp/cells/<cell>/mlflow` — `dsn` (Postgres DSN under
     the per-cell Postgres)
   - `secret/aqp/cells/<cell>/iceberg` — `jdbc_uri` + `username` +
     `password`
   The Phase 4 §7.6 `vault-secrets-operator` materialises these into
   Kubernetes `Secret` objects via the chart's `VaultStaticSecret` CRs.

3. **Operator (Phase 6.5) prerequisites installed cluster-wide.**
   - CloudNativePG operator (`postgresql.cnpg.io/v1`)
   - vault-secrets-operator (`secrets.hashicorp.com/v1beta1`)
   - Linkerd 2.16 (Phase 4 §7.1)

## Step 1 — Provision the per-cell data plane

Install the Helm chart for the target cell. The chart stamps a
CNPG `Cluster`, Redis StatefulSet, MinIO StatefulSet + bucket
bootstrap Job (with Object Lock COMPLIANCE on the `audit/` prefix),
MLflow Deployment, and Iceberg REST Deployment.

```bash
helm install data-plane aqp_platform/deployments/helm/aqp-cell-data-plane/ \
  --namespace cell-silo-reg-acme \
  --set cell_id=cell-silo-reg-acme \
  --set tier=silo-reg \
  --set region=us-east-1 \
  --set minio.replicas=4 \
  --set postgres.instances=3
```

Wait for every Pod to reach `Ready=true`. Then:

```bash
kubectl -n cell-silo-reg-acme get pods
kubectl -n cell-silo-reg-acme get vaultstaticsecret
kubectl -n cell-silo-reg-acme exec aqp-cell-postgres-1 -- psql -c "SELECT 1"
```

The MinIO bootstrap Job creates 4 buckets with Object Lock COMPLIANCE
on `aqp-cell-silo-reg-acme-audit` for 30 days; verify:

```bash
kubectl -n cell-silo-reg-acme exec deploy/aqp-cell-minio-bootstrap -- \
  mc retention info "cell/aqp-cell-silo-reg-acme-audit"
# expect: Mode=COMPLIANCE Validity=30d
```

## Step 2 — Run schema migrations against the new Postgres

Inside the cell namespace, run `alembic upgrade head` against the
per-cell DSN. The CNPG cluster ships the application schema only after
this step.

```bash
kubectl -n cell-silo-reg-acme run alembic --rm -it --image=ghcr.io/julianwiley/aqp-api:latest --restart=Never -- \
  alembic -c /app/alembic.ini upgrade head
```

The Alembic chain immutability check (`scripts/ci/check_migration_immutability.py`)
guarantees the same numeric head as the shared plane.

## Step 3 — Enable dual writes

Flip `AQP_CELL_DUAL_WRITE=true` in the **API** environment. This is the
critical safety window — once enabled, every new write goes to BOTH
planes (the shared cluster-wide plane AND the per-cell plane bound
via `RequestContext.cell_id`). It does NOT affect callers without an
active request context.

```bash
kubectl set env -n aqp deployment/aqp-core AQP_CELL_DUAL_WRITE=true
kubectl rollout status -n aqp deployment/aqp-core
```

Verify the new cells are reachable by issuing a noop write from a
test tenant pinned to the cell.

## Step 4 — Backfill historical rows

```bash
# Dry-run first to print row counts:
python scripts/cells/dual_write_backfill.py \
  --tenant tenant_acme \
  --target-cell cell-silo-reg-acme

# When the plan looks right, apply:
python scripts/cells/dual_write_backfill.py \
  --tenant tenant_acme \
  --target-cell cell-silo-reg-acme \
  --apply
```

The script copies every tenant-owned table (workspaces, strategy
specs, agent runs, bot runs, RL experiments, paper trading, dataset
specs, …) but never deletes from the source. It refuses to write if
the destination plane already has rows for the same tenant — that is
the idempotency guard against duplicate inserts.

## Step 5 — Reconcile

```bash
python scripts/cells/dual_write_backfill.py \
  --tenant tenant_acme \
  --target-cell cell-silo-reg-acme \
  --reconcile-only
```

Every table MUST show `OK` (matching row count AND matching SHA-256
roll-up). If even one shows `MISMATCH`, STOP — investigate before
proceeding. The script exits with code 2 on mismatch.

## Step 6 — Cutover

Mutate `tenant_cells.cell_id` for the tenant. This step is intentionally
NOT automated by the backfill script — operators run it manually so
the change generates an explicit `workload_runs` audit row.

```sql
-- in the SHARED plane
INSERT INTO workload_runs (organization_id, action, ...)
  VALUES ('tenant_acme', 'cell_cutover', ...);

UPDATE tenant_cells
   SET cell_id = 'cell-silo-reg-acme', cutover_at = NOW()
 WHERE tenant_id = 'tenant_acme';
```

The cell-router (Phase 3 §6.4) picks up the new mapping on the next
JWT exchange. Existing in-flight sessions stay bound to the source
plane until the next request — no in-flight rollback needed.

## Step 7 — Disable dual writes

```bash
kubectl set env -n aqp deployment/aqp-core AQP_CELL_DUAL_WRITE=false
kubectl rollout status -n aqp deployment/aqp-core
```

The tenant is now isolated in the cell data plane. The historical rows
remain in the shared plane (Phase 6 keeps them as the immutable
fallback path); a separate retention policy (90 days) prunes them
after sufficient bake time. Do NOT delete source rows from this
runbook.

## Reverting

If anything goes wrong between Step 3 and Step 6 you can revert
cleanly because writes are landing in BOTH planes. Set
`AQP_CELL_DUAL_WRITE=false`, restore the previous `tenant_cells.cell_id`,
and the tenant resumes on the shared plane.

After Step 6 the cutover is sticky — reverting requires running the
inverse backfill (`--tenant tenant_acme --target-cell cell-shared-std-local`)
and is a manual operation. Coordinate with the on-call.

## Audit trail

Every step writes audit rows:

- Step 1 (Helm install): captured by Argo CD's `Application` revision.
- Step 2 (`alembic upgrade head`): writes `alembic_version` in the
  per-cell Postgres.
- Step 3 (`AQP_CELL_DUAL_WRITE=true`): captured by
  `aqp_control_plane.audit.write_workload_run` when the env flip lands.
- Step 4-5 (backfill): the script logs to stdout AND writes a
  `cell_backfill_runs` row (Alembic 0085, future).
- Step 6 (cutover): the explicit `workload_runs` INSERT above.
- Step 7 (`AQP_CELL_DUAL_WRITE=false`): captured by
  `aqp_control_plane.audit.write_workload_run`.

The auditor SHOULD verify all seven rows exist before signing off on
the migration.
