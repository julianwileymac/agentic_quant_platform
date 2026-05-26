# Audit lake reconstruction runbook

Phase 7 §10 (`RESTRUCTURING_PLAN.md`) — operating procedure for the
hash-chained audit lake: hourly flush, transparency-log anchoring,
replay harness, and regulatory-grade evidence bundles.

This runbook is the canonical companion to:

| Surface | Path |
| --- | --- |
| Hourly flush task | `aqp/tasks/audit_lake_tasks.py::flush` |
| Anchor sinks | `aqp/audit/sinks/{rekor,qldb,rfc3161}.py` |
| Replay harness | `aqp/audit/replay.py` |
| Evidence bundle route | `aqp_control_plane/src/aqp_cp/api/routers/evidence_bundles.py` |
| Alembic migrations | `0085_audit_lake_anchors.py`, `0086_lineage_cell_id.py` |
| MinIO retention | `aqp_platform/deployments/helm/aqp-cell-data-plane/templates/minio.yaml` |
| OpenLineage relay extension | `aqp/audit/openlineage_anchor.py` |

## Architecture in one paragraph

The Postgres ``audit_log`` hash chain (Alembic 0079) is the hot write
path. Every hour the ``aqp.tasks.audit_lake_tasks.flush`` Celery beat
task seals the previous hour's segment, materialises it to
``aqp_gold_audit.events_<cell_id>`` via Iceberg, copies the manifest
to ``s3://aqp-<cell>-warehouse/audit/...`` with Object Lock COMPLIANCE,
and submits the segment tip-hash to every configured transparency-log
sink. The verification handle (Rekor entry UUID, QLDB document id,
RFC 3161 ``TimeStampResp``) lands in ``audit_lake_anchors``. The
``BipartiteGraphObserver`` (Phase 7 §10.3 + Alembic 0086) stamps
``cell_id`` on every new lineage row so downstream queries can join
audit + lineage by cell. Auditors call
``POST /manage/evidence-bundles`` to download a deterministic
``.tar.zst`` archive of every artifact needed to reconstruct an
event window.

## When to enable

Flip ``AQP_AUDIT_LAKE_ENABLED=true`` once:

1. Phase 6 §9.2 MinIO chart is rolled out per cell with
   ``objectLockOnAudit: true``.
2. ``objectLockRetention`` is set to the regulatory minimum
   (``7y`` for FINRA / SEC; ``30d`` for dev).
3. Alembic 0085 + 0086 have run against every per-cell Postgres.
4. At least one transparency sink is configured via
   ``AQP_AUDIT_TRANSPARENCY_SINKS`` (comma-separated:
   ``rekor`` / ``qldb`` / ``rfc3161``).

## Step 1 — Configure transparency sinks

| Sink | Use when | Required env |
| --- | --- | --- |
| **Rekor** (default) | Shared cells, public verifiability | `AQP_AUDIT_REKOR_URL` (default `https://rekor.sigstore.dev`) + Vault `secret/aqp/rekor/sigstore` with `signing_key_pem` + `signing_cert_pem` |
| **AWS QLDB** | `silo-reg` cells on AWS | `AQP_AUDIT_QLDB_LEDGER_NAME`, `AQP_AUDIT_QLDB_REGION`, AWS IAM role with `qldb:SendCommand` |
| **RFC 3161 TSA** | `silo-reg` cells on-prem | `AQP_AUDIT_RFC3161_TSA_URL` + Vault `secret/aqp/rfc3161/tsa:<alias>` with optional `client_cert_pem`/`client_key_pem` |

The three sinks are pluggable adapters of the
`TransparencyAnchorSink` ABC (`aqp/audit/protocol.py`). Operators MAY
ship a custom subclass; the metaclass auto-registers it as long as
it sets `sink_kind` and lives in an imported module.

Belt-and-braces example for a `silo-reg`-on-prem cell:

```bash
AQP_AUDIT_TRANSPARENCY_SINKS=rekor,rfc3161
```

The flush task tries every configured sink and records every
successful anchor as one row in `audit_lake_anchors`; an auditor
who needs cross-verification can pick whichever sink suits.

## Step 2 — Enable the hourly flush

```bash
# Per cell namespace.
kubectl set env -n cell-shared-std-us-east-1a deploy/aqp-core \
  AQP_AUDIT_LAKE_ENABLED=true \
  AQP_AUDIT_TRANSPARENCY_SINKS=rekor
kubectl rollout status -n cell-shared-std-us-east-1a deploy/aqp-core
```

The flush task is already registered in
`aqp/tasks/celery_app.py::beat_schedule` as `audit-lake-flush`
(default interval 3600 s). The settings layer (`aqp_lake_enabled=False`)
keeps it inert until you flip the switch.

Verify a single flush manually:

```bash
celery -A aqp.tasks.celery_app call aqp.tasks.audit_lake_tasks.flush
# Then inspect the new rows:
psql -c "SELECT cell_id, segment_start_ts, state, row_count, iceberg_snapshot_id FROM audit_lake_segments ORDER BY segment_start_ts DESC LIMIT 5"
```

A successful flush emits the OpenLineage `RunEvent`
`aqp/audit/segment-anchor` to the existing
`lineage_openlineage_outbox`; the Marquez relay carries it through
the standard pipeline.

## Step 3 — Verify a segment manually

```bash
python -c "
from aqp.audit import AnchorRecord
from aqp.audit.sinks import RekorSink
from datetime import datetime, timezone
from sqlalchemy import text
from aqp.persistence.db import get_session

with get_session() as s:
    row = s.execute(text(
        'SELECT * FROM audit_lake_segments WHERE cell_id = :c '
        'ORDER BY segment_start_ts DESC LIMIT 1'
    ), {'c': 'cell-shared-std-us-east-1a'}).first()
    anchor = s.execute(text(
        'SELECT * FROM audit_lake_anchors WHERE segment_id = :id AND sink_kind = :k'
    ), {'id': row.id, 'k': 'rekor'}).first()

record = AnchorRecord(
    cell_id=row.cell_id,
    segment_start_ts=row.segment_start_ts,
    segment_end_ts=row.segment_end_ts,
    prev_tip_hash=row.prev_segment_tip_hash,
    tip_hash=row.segment_tip_hash,
    iceberg_snapshot_id=row.iceberg_snapshot_id or '',
    s3_manifest_uri=row.s3_manifest_uri or '',
)
print(RekorSink().verify(record, anchor.verification_handle))
"
```

Should print `True`. If `False`, STOP and investigate before producing
any evidence bundles — the chain is broken or the anchor was tampered
with.

## Step 4 — Replay a recorded run

`aqp/audit/replay.py` re-executes a run against its hash-locked spec.

```python
from aqp.audit.replay import replay_run, ReplayEnvironment

report = replay_run(
    run_id="agent-run-abc123",
    cell_id="cell-shared-std-us-east-1a",
    target_environment=ReplayEnvironment.AUDIT_SHADOW,
)
print(report.to_dict())
```

The harness:

1. Looks up the run row in whichever runtime table contains the id.
2. Loads the immutable spec snapshot via ``<runtime>_spec_versions``.
3. Looks up the MCP tool descriptor hashes recorded at original
   run time.
4. Provisions a deterministic shadow Postgres schema named
   ``replay_<env>_<runtime>_<run-prefix>`` (see
   ``_shadow_schema_name``).
5. Verifies the anchored audit segment covering the run's timestamp.
6. Returns a :class:`ReplayReport` with `output_matches` /
   `anchor_verified` for sign-off.

The actual re-execution slot is currently a Phase 7.5 TODO — until
then `replay_output_hash` mirrors `original_output_hash` so the
report covers spec-pinning + anchor verification only. That's the
audit-essential surface.

## Step 5 — Produce an evidence bundle

```bash
curl -X POST https://manage.aqp.fund/manage/evidence-bundles \
  -H "Authorization: Bearer ${AQP_ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{
    "tenant_id": "tenant_acme",
    "cell_id": "cell-silo-reg-acme",
    "from_ts": "2026-05-01T00:00:00Z",
    "to_ts": "2026-05-31T23:59:59Z"
  }' \
  --output evidence-acme-may2026.tar.zst
```

The bundle contents (every part is a deterministic JSON file):

| File | Source |
| --- | --- |
| `manifest.json` | Top-level manifest with SHA-256 of every other part |
| `audit_rows.json` | Every `audit_log` row in the window |
| `audit_segments.json` | Every `audit_lake_segments` row + its anchors |
| `spec_snapshots.json` | Every immutable spec referenced by an audit row |
| `lineage.json` | Bipartite lineage rows for the same cell + window |

The manifest hash IS the canonical bundle id; auditors archive
``manifest.manifest_hash`` alongside the .tar.zst.

## Reverting

Phase 7 is incrementally adopted. Reverting is easy:

- `AQP_AUDIT_LAKE_ENABLED=false` — the task no-ops; existing data
  remains.
- `AQP_AUDIT_TRANSPARENCY_SINKS=` (empty) — the segment still flushes
  to Iceberg but no anchors are submitted.
- The Iceberg `aqp_gold_audit.events_<cell>` tables are read-only by
  policy; do NOT delete them. They are the cold-storage backup of
  the Postgres `audit_log`.
- MinIO Object Lock COMPLIANCE means the `audit/` prefix CANNOT be
  deleted by anyone — not even the root user — until retention
  expires. This is the regulatory commitment, not a bug.

## SLOs

| SLO | Target |
| --- | --- |
| Flush latency p99 | ≤ 5 minutes after segment close |
| Anchor latency p99 | ≤ 10 minutes after flush completes |
| Per-segment row throughput | ≥ 10 000 audit rows / minute |
| Evidence bundle build time | ≤ 30 s for a 30-day window |
| Anchor verify success rate | ≥ 99.9% (excluding Internet outage windows) |

## Where to file alerts

Prometheus + Alertmanager rules live in
`aqp_platform/deployments/kubernetes/base-services/prometheus-operator/`
(future Phase 7.5 deliverable). Until then, monitor:

- `audit_lake_segments.state = 'flushed'` rows that haven't progressed
  to `'anchored'` within 30 minutes — indicates sink failure.
- `audit_lake_anchors.last_verified_ok = FALSE` rows — indicates an
  anchor was tampered with or the sink is unreachable.
- `audit_log` insert errors with text `hash chain` — the Postgres
  trigger is rejecting a row.

## Audit trail of THIS subsystem

Every Phase 7 mutation lands in `workload_runs`:

- Flipping `AQP_AUDIT_LAKE_ENABLED` lands as an `apply_config` row.
- Each evidence-bundle export lands as an `evidence_bundle_export`
  row BEFORE the bytes leave the process (AGENTS rule 45).
- The hourly flush itself does NOT land a `workload_runs` row by
  design (it's a routine background task, not an operator action) —
  the per-segment write to `audit_lake_segments` IS the audit trail
  for the flush.
