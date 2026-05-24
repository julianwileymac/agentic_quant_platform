"""Emit OpenLineage / AQP LineageBus events on sync completion.

Phase 5 mounts the FastAPI webhook receiver; this module provides
the shared event-construction helpers so both the in-process
Dagster wrapper and the out-of-process Airbyte webhook produce
identical lineage events.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def emit_airbyte_sync_completed(
    *,
    connector_slug: str,
    stream: str,
    workspace_id: str,
    connection_id: str,
    rows_written: int,
    source_table_id: str | None = None,
    target_table_id: str | None = None,
    actor: str | None = None,
    actor_kind: str = "service",
) -> None:
    """Push a ``LineageEvent(transform_kind="airbyte.sync")`` onto the bus."""
    try:
        from aqp.data.catalog.lineage import LineageBus, LineageEvent

        event = LineageEvent(
            transform_kind="airbyte.sync",
            source_table_id=source_table_id
            or f"airbyte://workspace/{workspace_id}/connection/{connection_id}/{stream}",
            target_table_id=target_table_id
            or f"iceberg://aqp_bronze_airbyte_{connector_slug}/{stream}",
            rows_written=rows_written,
            service_name=f"airbyte:{connector_slug}",
            medallion_layer="bronze",
            actor=actor,
            actor_kind=actor_kind,
            summary=f"airbyte sync {connector_slug}/{stream}: {rows_written} rows",
            details={
                "connector_slug": connector_slug,
                "workspace_id": workspace_id,
                "connection_id": connection_id,
                "stream": stream,
            },
        )
        LineageBus.publish(event)
    except Exception as exc:  # noqa: BLE001
        logger.debug("emit_airbyte_sync_completed failed: %s", exc)


__all__ = ["emit_airbyte_sync_completed"]
