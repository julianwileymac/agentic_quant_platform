"""OpenLineage outbox extension for audit-segment anchors (Phase 7 §10.1).

After each :func:`aqp.tasks.audit_lake_tasks.flush` cycle marks a
segment ``state='anchored'``, this module appends one
``audit_segment_anchor`` OpenLineage ``RunEvent`` to the existing
``lineage_openlineage_outbox`` table (Alembic 0060). The relay
(:mod:`aqp.lineage.openlineage.relay`) then POSTs it to Marquez
alongside every other lineage event, so the per-cell audit chain
shows up in the same observability surface.

The ``RunEvent`` carries:

- ``job`` — ``aqp/audit/segment-anchor`` (constant per cell).
- ``run`` — UUID per segment (the ``audit_lake_segments.id``).
- ``inputs`` — a single dataset entry that points at the previous
  segment's tip hash + the Iceberg snapshot for the current segment.
- ``outputs`` — empty; segment anchors emit a state record, not a
  dataset.
- ``facets`` — embeds the segment's ``prev_tip_hash`` + ``tip_hash``
  + every transparency-log verification handle so Marquez can replay
  the chain without touching Postgres.

We DELIBERATELY bypass the :class:`LineageBus` here — the segment
anchor is an audit-time signal, not a data-motion event, so it
shouldn't trigger any of the standard observers (which would attempt
to write a `lineage_transform_vertex` for it).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


JOB_NAMESPACE = "aqp"
JOB_NAME = "audit/segment-anchor"


def _outbox_row(
    *,
    cell_id: str,
    segment_id: str,
    segment_start_ts: datetime,
    segment_end_ts: datetime,
    prev_tip_hash: bytes | None,
    tip_hash: bytes,
    iceberg_snapshot_id: str,
    s3_manifest_uri: str,
    anchors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the ``lineage_openlineage_outbox`` row + the embedded payload.

    The outer dict matches the column shape of the outbox table; the
    ``payload`` value is the OpenLineage ``RunEvent`` JSON object.
    """
    run_id = segment_id  # one run per segment
    event_time = segment_end_ts.isoformat() + "Z"

    facets: dict[str, Any] = {
        "aqp_audit_segment": {
            "_producer": "aqp",
            "_schemaURL": "https://aqp.fund/schemas/audit-segment-anchor/v1",
            "cell_id": cell_id,
            "segment_start_ts": segment_start_ts.isoformat(),
            "segment_end_ts": segment_end_ts.isoformat(),
            "prev_tip_hash": prev_tip_hash.hex() if prev_tip_hash else None,
            "tip_hash": tip_hash.hex(),
            "iceberg_snapshot_id": iceberg_snapshot_id,
            "s3_manifest_uri": s3_manifest_uri,
            "anchors": [
                {
                    "sink_kind": a.get("sink_kind") or a.get("kind"),
                    "verification_handle": a.get("verification_handle")
                    or a.get("handle"),
                    "verification_url": a.get("verification_url"),
                }
                for a in anchors
                if a.get("ok", True)
            ],
        },
    }

    payload: dict[str, Any] = {
        "eventType": "COMPLETE",
        "eventTime": event_time,
        "producer": "aqp/audit_lake_tasks",
        "schemaURL": (
            "https://openlineage.io/spec/2-0-2/OpenLineage.json#/$defs/RunEvent"
        ),
        "run": {"runId": run_id, "facets": facets},
        "job": {
            "namespace": JOB_NAMESPACE,
            "name": JOB_NAME,
            "facets": {
                "documentation": {
                    "_producer": "aqp",
                    "_schemaURL": (
                        "https://openlineage.io/spec/facets/1-0-1/"
                        "DocumentationJobFacet.json"
                    ),
                    "description": (
                        "Hourly audit-segment anchor emission (Phase 7 §10.1). "
                        "Each event represents one sealed audit_log segment for "
                        "the given cell; the run facets carry the segment tip "
                        "hashes + every transparency-log verification handle."
                    ),
                }
            },
        },
        "inputs": [
            {
                "namespace": JOB_NAMESPACE,
                "name": (
                    f"audit_log.{cell_id}."
                    f"{segment_start_ts.strftime('%Y%m%dT%H%M')}"
                ),
            }
        ],
        "outputs": [],
    }

    row: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "payload": payload,
        "eventType": "COMPLETE",
        "job_namespace": JOB_NAMESPACE,
        "job_name": JOB_NAME,
        "run_id": run_id,
    }
    return row


def write_anchor_to_outbox(
    *,
    cell_id: str,
    segment_id: str,
    segment_start_ts: datetime,
    segment_end_ts: datetime,
    prev_tip_hash: bytes | None,
    tip_hash: bytes,
    iceberg_snapshot_id: str,
    s3_manifest_uri: str,
    anchors: list[dict[str, Any]],
) -> str:
    """Append a segment-anchor row to ``lineage_openlineage_outbox``.

    Returns the new outbox-row id, or an empty string when the outbox
    is disabled / unreachable (defensive: never block the flush task).
    """
    try:
        from aqp.config import settings

        if not bool(getattr(settings, "lineage_openlineage_relay_enabled", False)):
            return ""
    except Exception:  # noqa: BLE001 - defensive
        return ""

    try:
        from sqlalchemy import text

        from aqp.persistence.db import get_session
    except Exception:  # noqa: BLE001 - defensive
        return ""

    row = _outbox_row(
        cell_id=cell_id,
        segment_id=segment_id,
        segment_start_ts=segment_start_ts,
        segment_end_ts=segment_end_ts,
        prev_tip_hash=prev_tip_hash,
        tip_hash=tip_hash,
        iceberg_snapshot_id=iceberg_snapshot_id,
        s3_manifest_uri=s3_manifest_uri,
        anchors=anchors,
    )

    try:
        with get_session() as session:
            session.execute(
                text(
                    """
                    INSERT INTO lineage_openlineage_outbox (
                        id, payload, "eventType", job_namespace, job_name,
                        run_id, created_at
                    ) VALUES (
                        :id, :payload, :event_type, :job_namespace, :job_name,
                        :run_id, :created_at
                    )
                    """
                ),
                {
                    "id": row["id"],
                    "payload": json.dumps(row["payload"]),
                    "event_type": row["eventType"],
                    "job_namespace": row["job_namespace"],
                    "job_name": row["job_name"],
                    "run_id": row["run_id"],
                    "created_at": datetime.utcnow(),
                },
            )
    except Exception:  # noqa: BLE001 - never break the flush task
        logger.warning("audit anchor outbox write failed", exc_info=True)
        return ""
    return row["id"]


__all__ = ["write_anchor_to_outbox", "JOB_NAMESPACE", "JOB_NAME"]
