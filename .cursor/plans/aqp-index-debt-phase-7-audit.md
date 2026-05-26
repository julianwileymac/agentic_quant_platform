# aqp_index debt — Phase 7 audit immutability & reconstruction

Triggered by: `RESTRUCTURING_PLAN.md` §10 implementation
(hash-chained audit lake to Object Lock + transparency anchor sinks +
replay harness + evidence bundles + cell-aware lineage).

## Qualifying surfaces

The curator MUST refresh the `aqp_index/` pointers for the following
surfaces. Each entry lists the file the curator would update and the
new signature / pointer it should record.

### 1. `aqp/audit/`

- **New package**: `aqp/audit/{__init__,protocol}.py` +
  `aqp/audit/sinks/{__init__,rekor,qldb,rfc3161}.py`.
- **TransparencyAnchorSink ABC** + auto-registering metaclass mirrors
  `IdentityProviderMeta` / `SecretStoreMeta` / `TenancyStrategyMeta`.
- **AnchorRecord dataclass** carries the segment metadata the sinks
  submit to their underlying logs.
- **Three sinks**: Rekor (default), QLDB (silo-reg-on-AWS), RFC 3161
  TSA (silo-reg-on-prem).
- Curator should record the abstract base + every concrete subclass
  with its `sink_kind` discriminator.

### 2. `aqp/audit/replay.py`

- **New module**: `replay_run(...)` re-executes a recorded run against
  its hash-locked spec.
- :class:`ReplayEnvironment` enum (`AUDIT_SHADOW`, `INCIDENT_REPRO`,
  `MODEL_REVALIDATION`).
- :class:`ReplayReport` dataclass — the public return shape.
- Shadow Postgres schema lifecycle via `_ensure_shadow_schema` +
  `_drop_shadow_schema`.

### 3. `aqp/audit/openlineage_anchor.py`

- **New module**: extends the existing
  `lineage_openlineage_outbox` (Alembic 0060) with an
  `audit_segment_anchor` `RunEvent` per anchored segment.
- Marquez sees the audit chain in the same observability surface as
  every other lineage event.

### 4. `aqp/tasks/audit_lake_tasks.py`

- **New Celery beat task** `aqp.tasks.audit_lake_tasks.flush` —
  hourly per the new `audit-lake-flush` entry in
  `aqp/tasks/celery_app.py::beat_schedule`.
- Iterates over every active cell, seals the previous hour's segment,
  materialises to Iceberg + per-cell MinIO `audit/...`, anchors to
  every configured `TransparencyAnchorSink`, persists the verification
  handles in `audit_lake_anchors`, and emits an OpenLineage anchor
  event.

### 5. `aqp/lineage/graph/writer.py`

- **New helper**: `_resolve_cell_id_from_event(event)` consults the
  Phase 3 §6.3 runtime context + `settings.cell_default_id`.
- **Modified**: `_stamp_tenancy` now stamps `cell_id` on lineage
  rows when the ORM column exists.

### 6. `aqp/persistence/models_lineage_graph.py`

- **Modified**: `DatasetVertex`, `TransformVertex`, and
  `LineageEdge` all carry a nullable `cell_id` column (matches
  Alembic 0086).

### 7. `aqp/config/settings.py`

- **New settings**: `audit_lake_enabled`, `audit_lake_segment_minutes`,
  `audit_lake_flush_interval_seconds`, `audit_transparency_sinks`,
  `audit_rekor_url`, `audit_qldb_ledger_name`, `audit_qldb_region`,
  `audit_rfc3161_tsa_alias`, `audit_rfc3161_tsa_url`.
- `.env.example` updated with the new `AQP_AUDIT_*` env vars.

### 8. `aqp_platform_core/.../models/workloads.py`

- **New enum entry**: `WorkloadAction.EVIDENCE_BUNDLE_EXPORT`. Every
  evidence-bundle download lands in `workload_runs` BEFORE bytes
  leave the process (AGENTS rule 45).

### 9. `aqp_control_plane/.../api/routers/evidence_bundles.py`

- **New router**: `POST /manage/evidence-bundles` returns a
  deterministic `.tar.zst` archive of audit + transparency anchor +
  spec snapshot + lineage rows for `(tenant_id, cell_id, date_range)`.
- Registered in `aqp_cp/main.py` under the existing router fan-out.

### 10. Alembic 0085 + 0086

- **0085_audit_lake_anchors**: creates `audit_lake_segments` +
  `audit_lake_anchors`.
- **0086_lineage_cell_id**: adds `cell_id` to
  `lineage_dataset_vertex`, `lineage_transform_vertex`,
  `lineage_edge`, `lineage_openlineage_outbox`,
  `lineage_signing_key_archive`.
- `.hashes.lock` updated with both new revisions.

### 11. `aqp_platform/deployments/helm/aqp-cell-data-plane/`

- **Modified**: `values.yaml` adds `minio.objectLockRetention` (dev
  default `30d`; prod MUST override to `7y`).
- **Modified**: `templates/minio.yaml` interpolates the retention
  value into the MinIO bootstrap Job's `mc retention set --default
  COMPLIANCE <retention>` command.

### 12. `aqp_docs/docs/how-to/audit-lake-reconstruction.md`

- **New runbook**: step-by-step procedure for enabling the audit
  lake, verifying segments, replaying runs, and producing evidence
  bundles.

## Why a curator pass is needed

Phase 7 introduces a NEW subsystem (the audit lake + transparency
anchor mesh) that ties together the Phase 3 cell registry, Phase 5
hash-locked specs, Phase 5 MCP descriptor hashes, and Phase 6
per-cell MinIO. Without an `aqp_index/` refresh, agents will continue
to miss:

- the `TransparencyAnchorSink` ABC + the three concrete sinks
- the `replay_run` / `ReplayReport` surface
- the new `/manage/evidence-bundles` route
- the `cell_id` ORM columns on lineage tables
- the new beat task + the `AQP_AUDIT_*` settings

## Curator entry-point (when run)

```bash
codex run-agent aqp-index-curator \
  --reason "Phase 7 audit immutability & reconstruction" \
  --surfaces "aqp/audit/,aqp/audit/sinks/,aqp/audit/replay.py,aqp/audit/openlineage_anchor.py,aqp/tasks/audit_lake_tasks.py,aqp/lineage/graph/writer.py,aqp/persistence/models_lineage_graph.py,aqp/config/settings.py,aqp_platform_core/src/aqp_platform_core/models/workloads.py,aqp_control_plane/src/aqp_cp/api/routers/evidence_bundles.py,alembic/versions/0085_audit_lake_anchors.py,alembic/versions/0086_lineage_cell_id.py,aqp_platform/deployments/helm/aqp-cell-data-plane/values.yaml,aqp_platform/deployments/helm/aqp-cell-data-plane/templates/minio.yaml,aqp_docs/docs/how-to/audit-lake-reconstruction.md"
```
