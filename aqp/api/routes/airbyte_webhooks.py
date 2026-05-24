"""Airbyte sync webhook → OpenLineage → LineageBus (Phase 5).

Closes the gap documented in the planning exploration: today
``AirbyteConnectionRow.last_sync_status`` is updated passively by
the discovery collator; no ``LineageEvent`` fires on sync
completion. This webhook receives Airbyte's outbound OpenLineage
payload (Airbyte ships an OL emitter natively) and translates each
``RunEvent`` into the AQP ``LineageEvent`` shape the bipartite
graph + the bipartite UI consume.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/airbyte/webhooks", tags=["airbyte", "webhooks"])


@router.post("/sync_complete")
async def airbyte_sync_complete(request: Request) -> dict[str, Any]:
    """Receive an Airbyte OpenLineage ``RunEvent`` and emit ``LineageEvent``.

    Airbyte's outbound OpenLineage payload shape (per the spec):
    ``{run, job, inputs[], outputs[], producer, eventTime, eventType}``.
    We extract the connector slug from the ``job.name`` and the
    stream from each output's ``name``, then emit one
    ``LineageEvent(transform_kind="airbyte.sync")`` per stream.
    """
    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"invalid json: {exc}") from exc
    job = payload.get("job") or {}
    run = payload.get("run") or {}
    inputs = payload.get("inputs") or []
    outputs = payload.get("outputs") or []
    event_time = payload.get("eventTime")
    event_type = payload.get("eventType")

    connector_slug = str(job.get("name") or "unknown").split(".")[-1]
    run_id = str(run.get("runId") or "")

    emitted = 0
    try:
        from aqp_ingest_cdk.lineage import emit_airbyte_sync_completed

        # When there are no outputs we can't fan out per-stream;
        # still emit a single sync event so the run shows up.
        if not outputs:
            outputs = [{"name": "default"}]
        for output in outputs:
            stream = str(output.get("name") or "default")
            stats = (
                (output.get("outputFacets") or {}).get("outputStatistics") or {}
            )
            rows_written = int(stats.get("rowCount") or 0)
            emit_airbyte_sync_completed(
                connector_slug=connector_slug,
                stream=stream,
                workspace_id=str(run.get("namespace") or ""),
                connection_id=run_id,
                rows_written=rows_written,
            )
            emitted += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("airbyte webhook emit failed: %s", exc)

    return {
        "ok": True,
        "connector_slug": connector_slug,
        "run_id": run_id,
        "event_type": event_type,
        "event_time": event_time,
        "inputs": len(inputs),
        "outputs_emitted": emitted,
    }


__all__ = ["router"]
