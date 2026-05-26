"""Audit-lake hourly flush + anchor Celery beat task (Phase 7 §10.1).

Materialises closed ``audit_log`` segments to Iceberg + the per-cell
MinIO ``audit/`` prefix, then submits the segment tip-hash to every
configured transparency-log sink. The task is idempotent: each segment
is identified by ``(cell_id, segment_start_ts)`` and a re-run skips
already-flushed segments.

Hard rules honoured:

- **Rule 3 (Iceberg writes)** — segments are materialised through
  :func:`aqp.data.iceberg_catalog.append_arrow`. Never raw PyIceberg.
- **Rule 4 (Celery progress)** — every emit goes through
  :func:`emit` / :func:`emit_done` / :func:`emit_error`.
- **Rule 5 (Cross-task state)** — segment progress is persisted in
  ``audit_lake_segments`` (Alembic 0085); no pickled ORM objects.
- **Rule 7 (Configuration)** — every tunable comes through
  :class:`aqp.config.settings`. New env vars under
  ``AQP_AUDIT_LAKE_*`` and ``AQP_AUDIT_TRANSPARENCY_*``.
- **Phase 6 §9.3 cell-awareness** — the task iterates per active cell
  via :class:`DeploymentTopology.active_cells` so each cell's segments
  land in its own MinIO bucket (``aqp-<cell-id>-warehouse/audit/``).
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------


def _audit_lake_enabled() -> bool:
    try:
        from aqp.config import settings

        return bool(getattr(settings, "audit_lake_enabled", False))
    except Exception:  # noqa: BLE001 - defensive
        return False


def _segment_minutes() -> int:
    try:
        from aqp.config import settings

        return int(getattr(settings, "audit_lake_segment_minutes", 60))
    except Exception:  # noqa: BLE001
        return 60


def _transparency_sink_kinds() -> list[str]:
    """Return the comma-separated list of sink kinds to anchor against."""
    try:
        from aqp.config import settings

        raw = str(getattr(settings, "audit_transparency_sinks", "") or "")
    except Exception:  # noqa: BLE001
        raw = ""
    if not raw:
        return []
    return [kind.strip() for kind in raw.split(",") if kind.strip()]


# ---------------------------------------------------------------------------
# Iceberg-write helpers
# ---------------------------------------------------------------------------


def _bucket_prefix(cell_id: str) -> str:
    """Best-effort per-cell MinIO bucket prefix.

    Reads the topology data plane for the cell; falls back to
    ``aqp-cell-<id>`` if no override is set. The Phase 6 §9.2 MinIO
    bootstrap Job creates the matching bucket on every cell install.
    """
    try:
        from aqp.deployment.topology import get_deployment_topology

        topo = get_deployment_topology()
        cell = topo.cell_map.get(cell_id)
        if cell is not None:
            override = (cell.data_plane.minio_bucket_prefix or "").strip()
            if override:
                return override
    except Exception:  # noqa: BLE001 - defensive
        pass
    return f"aqp-cell-{cell_id}"


def _manifest_uri(cell_id: str, segment_start: datetime, snapshot_id: str) -> str:
    """Return the canonical s3:// URI for a segment manifest."""
    prefix = _bucket_prefix(cell_id)
    date = segment_start.astimezone(timezone.utc)
    return (
        f"s3://{prefix}-warehouse/audit/"
        f"{date:%Y}/{date:%m}/{date:%d}/{date:%H}-"
        f"{snapshot_id}.parquet"
    )


def _flush_segment_to_iceberg(
    *,
    cell_id: str,
    segment_start: datetime,
    segment_end: datetime,
    rows: list[dict[str, Any]],
) -> str:
    """Append a sealed segment to the cell's Iceberg audit lake table.

    Returns the new Iceberg snapshot id so the segment row can be
    cross-referenced from ``audit_lake_segments.iceberg_snapshot_id``.
    """
    if not rows:
        return ""

    # Lazy import — pyarrow is an optional extra.
    try:
        import pyarrow as pa  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "audit_lake_tasks requires pyarrow. Install the [iceberg] extra."
        ) from exc

    from aqp.data.iceberg_catalog import append_arrow, load_table

    table_name = f"aqp_gold_audit.events_{cell_id.replace('-', '_')}"
    arrow_table = pa.Table.from_pylist(rows)
    append_arrow(
        identifier=table_name,
        arrow=arrow_table,
        business_metadata=None,  # audit lake bypasses business validation
    )
    handle = load_table(table_name)
    if handle is None:
        return ""
    snapshot = handle.current_snapshot()
    return str(snapshot.snapshot_id) if snapshot is not None else ""


# ---------------------------------------------------------------------------
# Hash chain helpers
# ---------------------------------------------------------------------------


def _segment_tip_hash(rows: list[dict[str, Any]]) -> bytes:
    """Tip hash = last row's ``hash`` (the audit_log Postgres trigger fills it).

    Empty segments hash to the empty SHA-256 digest; that's deterministic
    and lets the reconstruction harness handle empty hours.
    """
    if not rows:
        return hashlib.sha256(b"").digest()
    last = rows[-1]
    last_hash = last.get("hash")
    if isinstance(last_hash, (bytes, bytearray)):
        return bytes(last_hash)
    if isinstance(last_hash, str):
        try:
            return bytes.fromhex(last_hash)
        except ValueError:
            return hashlib.sha256(last_hash.encode("utf-8")).digest()
    return hashlib.sha256(b"").digest()


# ---------------------------------------------------------------------------
# Core flush
# ---------------------------------------------------------------------------


def _flush_one_cell(cell_id: str, segment_start: datetime, segment_end: datetime) -> dict[str, Any]:
    """Flush a single ``(cell, window)`` segment end-to-end.

    Returns a summary dict suitable for the Celery emit_done payload.
    The function is idempotent — if the segment is already flushed it
    short-circuits and re-anchors only missing sinks.
    """
    from aqp.persistence.db import get_session

    summary: dict[str, Any] = {
        "cell_id": cell_id,
        "segment_start_ts": segment_start.isoformat(),
        "segment_end_ts": segment_end.isoformat(),
        "row_count": 0,
        "iceberg_snapshot_id": "",
        "s3_manifest_uri": "",
        "anchors": [],
        "state": "noop",
    }

    with get_session() as session:
        # 1. Read closed audit rows for this segment from the per-cell engine.
        from sqlalchemy import text

        result = session.execute(
            text(
                """
                SELECT id, cell_id, owner_user_id, workspace_id, ts,
                       event_category, event_type, actor_kind,
                       agent_subject, on_behalf_of_user_id,
                       tool_id, approval_id, template_id, connection_id,
                       request_id, details, prev_hash, hash
                  FROM audit_log
                 WHERE cell_id = :cell_id
                   AND ts >= :segment_start
                   AND ts <  :segment_end
                 ORDER BY ts ASC, id ASC
                """
            ),
            {
                "cell_id": cell_id,
                "segment_start": segment_start,
                "segment_end": segment_end,
            },
        )
        rows: list[dict[str, Any]] = [dict(r._mapping) for r in result]
        summary["row_count"] = len(rows)

        if not rows:
            summary["state"] = "empty"
            return summary

        # 2. Look up or create the segment row in audit_lake_segments.
        existing = session.execute(
            text(
                """
                SELECT id, state, iceberg_snapshot_id, s3_manifest_uri,
                       segment_tip_hash, prev_segment_tip_hash
                  FROM audit_lake_segments
                 WHERE cell_id = :cell_id
                   AND segment_start_ts = :segment_start
                """
            ),
            {"cell_id": cell_id, "segment_start": segment_start},
        ).first()

        if existing is not None and existing.state == "anchored":
            summary["state"] = "already_anchored"
            summary["iceberg_snapshot_id"] = existing.iceberg_snapshot_id or ""
            summary["s3_manifest_uri"] = existing.s3_manifest_uri or ""
            return summary

        # 3. Compute the segment hashes.
        prev_tip = session.execute(
            text(
                """
                SELECT segment_tip_hash
                  FROM audit_lake_segments
                 WHERE cell_id = :cell_id
                   AND segment_end_ts <= :segment_start
                 ORDER BY segment_end_ts DESC
                 LIMIT 1
                """
            ),
            {"cell_id": cell_id, "segment_start": segment_start},
        ).scalar_one_or_none()
        tip_hash = _segment_tip_hash(rows)

        # 4. Flush to Iceberg.
        snapshot_id = _flush_segment_to_iceberg(
            cell_id=cell_id,
            segment_start=segment_start,
            segment_end=segment_end,
            rows=rows,
        )
        manifest_uri = _manifest_uri(cell_id, segment_start, snapshot_id or "no-snapshot")

        # 5. Upsert the segment row.
        if existing is None:
            segment_id = str(uuid.uuid4())
            session.execute(
                text(
                    """
                    INSERT INTO audit_lake_segments (
                        id, cell_id, segment_start_ts, segment_end_ts,
                        prev_segment_tip_hash, segment_tip_hash,
                        row_count, iceberg_snapshot_id, s3_manifest_uri,
                        state, flushed_at, meta_json
                    ) VALUES (
                        :id, :cell_id, :segment_start, :segment_end,
                        :prev_tip, :tip,
                        :row_count, :snapshot_id, :manifest_uri,
                        'flushed', :flushed_at, '{}'
                    )
                    """
                ),
                {
                    "id": segment_id,
                    "cell_id": cell_id,
                    "segment_start": segment_start,
                    "segment_end": segment_end,
                    "prev_tip": prev_tip,
                    "tip": tip_hash,
                    "row_count": len(rows),
                    "snapshot_id": snapshot_id,
                    "manifest_uri": manifest_uri,
                    "flushed_at": datetime.now(timezone.utc),
                },
            )
        else:
            segment_id = existing.id
            session.execute(
                text(
                    """
                    UPDATE audit_lake_segments
                       SET segment_tip_hash = :tip,
                           prev_segment_tip_hash = :prev_tip,
                           row_count = :row_count,
                           iceberg_snapshot_id = :snapshot_id,
                           s3_manifest_uri = :manifest_uri,
                           state = 'flushed',
                           flushed_at = :flushed_at
                     WHERE id = :id
                    """
                ),
                {
                    "id": segment_id,
                    "tip": tip_hash,
                    "prev_tip": prev_tip,
                    "row_count": len(rows),
                    "snapshot_id": snapshot_id,
                    "manifest_uri": manifest_uri,
                    "flushed_at": datetime.now(timezone.utc),
                },
            )

        summary["iceberg_snapshot_id"] = snapshot_id
        summary["s3_manifest_uri"] = manifest_uri
        summary["state"] = "flushed"

        # 6. Anchor to every configured transparency sink.
        sink_kinds = _transparency_sink_kinds()
        if not sink_kinds:
            return summary

        # Resolve sink classes via the registry.
        from aqp.audit import (
            AnchorRecord,
            list_transparency_anchor_sink_classes,
        )

        # Force import of the concrete sinks so the metaclass registers them.
        from aqp.audit import sinks as _sinks  # noqa: F401 - registration import

        sink_map = list_transparency_anchor_sink_classes()
        record = AnchorRecord(
            cell_id=cell_id,
            segment_start_ts=segment_start,
            segment_end_ts=segment_end,
            prev_tip_hash=prev_tip,
            tip_hash=tip_hash,
            iceberg_snapshot_id=snapshot_id,
            s3_manifest_uri=manifest_uri,
        )
        anchors_summary: list[dict[str, Any]] = []
        for kind in sink_kinds:
            sink_cls = next(
                (
                    cls
                    for cls in sink_map.values()
                    if cls.sink_kind == kind
                ),
                None,
            )
            if sink_cls is None:
                anchors_summary.append({"kind": kind, "ok": False, "error": "no_sink"})
                continue
            try:
                sink = sink_cls()
                handle = sink.anchor(record)
            except Exception as exc:  # noqa: BLE001 - per-sink isolation
                logger.exception("anchor sink %s failed", kind)
                anchors_summary.append({"kind": kind, "ok": False, "error": str(exc)})
                continue
            anchor_id = str(uuid.uuid4())
            session.execute(
                text(
                    """
                    INSERT INTO audit_lake_anchors (
                        id, segment_id, sink_kind, verification_handle,
                        anchored_at, meta_json
                    ) VALUES (
                        :id, :segment_id, :sink_kind, :handle,
                        :anchored_at, '{}'
                    )
                    ON CONFLICT (segment_id, sink_kind) DO UPDATE
                        SET verification_handle = EXCLUDED.verification_handle,
                            anchored_at = EXCLUDED.anchored_at
                    """
                ),
                {
                    "id": anchor_id,
                    "segment_id": segment_id,
                    "sink_kind": kind,
                    "handle": handle,
                    "anchored_at": datetime.now(timezone.utc),
                },
            )
            anchors_summary.append({"kind": kind, "ok": True, "handle": handle[:24]})

        # 7. Mark the segment fully anchored if at least one sink succeeded.
        if any(a["ok"] for a in anchors_summary):
            session.execute(
                text(
                    """
                    UPDATE audit_lake_segments
                       SET state = 'anchored',
                           anchored_at = :anchored_at
                     WHERE id = :id
                    """
                ),
                {"id": segment_id, "anchored_at": datetime.now(timezone.utc)},
            )
            summary["state"] = "anchored"

            # Phase 7 §10.1 — emit a segment-anchor RunEvent into the
            # OpenLineage outbox so Marquez carries the audit chain too.
            try:
                from aqp.audit.openlineage_anchor import write_anchor_to_outbox

                write_anchor_to_outbox(
                    cell_id=cell_id,
                    segment_id=segment_id,
                    segment_start_ts=segment_start,
                    segment_end_ts=segment_end,
                    prev_tip_hash=prev_tip,
                    tip_hash=tip_hash,
                    iceberg_snapshot_id=snapshot_id,
                    s3_manifest_uri=manifest_uri,
                    anchors=[
                        {
                            "sink_kind": a["kind"],
                            "verification_handle": a.get("handle", ""),
                            "ok": a["ok"],
                        }
                        for a in anchors_summary
                    ],
                )
            except Exception:  # noqa: BLE001 - openlineage is best-effort
                logger.warning(
                    "audit anchor openlineage outbox write failed", exc_info=True
                )

        summary["anchors"] = anchors_summary
    return summary


def _planned_segment(now: datetime) -> tuple[datetime, datetime]:
    """Return ``(segment_start, segment_end)`` for the most-recent closed window.

    The audit lake intentionally flushes the segment that ENDED at the
    previous hour boundary, never the current open hour — that way no
    new rows can land inside an already-flushed window.
    """
    minutes = _segment_minutes()
    bucket = now.replace(minute=0, second=0, microsecond=0)
    # Snap to the most recent boundary <= now.
    end_floor = bucket.replace(
        minute=(now.minute // minutes) * minutes,
        second=0,
        microsecond=0,
    )
    if end_floor > now:
        end_floor = end_floor - timedelta(minutes=minutes)
    segment_end = end_floor
    segment_start = segment_end - timedelta(minutes=minutes)
    return segment_start, segment_end


def _active_cell_ids() -> list[str]:
    """Return every ``state='active'`` cell id from topology."""
    try:
        from aqp.deployment.topology import get_deployment_topology

        topo = get_deployment_topology()
    except Exception:  # noqa: BLE001 - defensive
        return []
    return [c.id for c in topo.active_cells()]


def _impl(task_id: str) -> dict[str, Any]:
    if not _audit_lake_enabled():
        emit_done(
            task_id,
            {"ok": True, "skipped": True, "reason": "disabled"},
        )
        return {"ok": True, "skipped": True}

    emit(task_id, "plan", "computing the closed segment window")
    now = datetime.now(timezone.utc)
    segment_start, segment_end = _planned_segment(now)
    cell_ids = _active_cell_ids()

    if not cell_ids:
        emit_done(
            task_id,
            {"ok": True, "skipped": True, "reason": "no_active_cells"},
        )
        return {"ok": True, "skipped": True}

    emit(
        task_id,
        "flush",
        f"flushing {len(cell_ids)} cells for window {segment_start.isoformat()}",
        cells=cell_ids,
    )

    results: list[dict[str, Any]] = []
    for cell_id in cell_ids:
        try:
            results.append(_flush_one_cell(cell_id, segment_start, segment_end))
        except Exception as exc:  # noqa: BLE001 - isolate per-cell failures
            logger.exception("audit_lake flush failed for cell %s", cell_id)
            results.append(
                {
                    "cell_id": cell_id,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    summary = {
        "ok": True,
        "segment_start": segment_start.isoformat(),
        "segment_end": segment_end.isoformat(),
        "cells": results,
    }
    emit_done(task_id, summary)
    return summary


@celery_app.task(
    bind=True,
    name="aqp.tasks.audit_lake_tasks.flush",
)
def flush(self) -> dict[str, Any]:
    """Celery beat entry point — flush + anchor the previous segment.

    Schedule hourly via :class:`celery.schedules.crontab` (``minute=5``
    is conventional so the segment is fully closed before the task
    runs). The function is safe to invoke ad-hoc from tests.
    """
    task_id = self.request.id or "audit-lake-flush"
    try:
        return _impl(task_id)
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, str(exc))
        logger.exception("audit_lake flush task failed")
        raise


__all__ = ["flush"]
