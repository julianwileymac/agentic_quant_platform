"""Emit ``LineageEvent(transform_kind="dbt.run")`` after every dbt run.

The Phase 2 ``DbtRunnerService.invoke`` calls this on completion so
every materialized model produces a lineage event. The bipartite
graph observer (rule 48) then dual-writes it into the
``lineage_*`` tables for the Vite /data/lineage view.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def emit_dbt_run_lineage(
    *,
    run_results: dict[str, Any],
    manifest_models: list[dict[str, Any]],
    project_slug: str = "core",
    actor: str | None = None,
    actor_kind: str = "service",
) -> int:
    """Emit one ``LineageEvent`` per successfully-built model."""
    if not run_results or not manifest_models:
        return 0
    try:
        from aqp.data.catalog.lineage import LineageBus, LineageEvent
    except Exception as exc:  # noqa: BLE001
        logger.debug("LineageBus unavailable: %s", exc)
        return 0
    by_unique_id = {m.get("unique_id"): m for m in manifest_models if m.get("unique_id")}
    emitted = 0
    for result in (run_results.get("results") or []):
        unique_id = result.get("unique_id")
        if not unique_id or result.get("status") != "success":
            continue
        node = by_unique_id.get(unique_id)
        if node is None:
            continue
        schema = node.get("schema") or ""
        name = node.get("name") or ""
        target_id = f"dbt://{project_slug}/{schema}/{name}"
        try:
            event = LineageEvent(
                transform_kind="dbt.run",
                target_table_id=target_id,
                service_name=f"dbt:{project_slug}",
                medallion_layer=node.get("config", {}).get("meta", {}).get(
                    "medallion_layer"
                ),
                actor=actor,
                actor_kind=actor_kind,
                summary=f"dbt run {project_slug}/{name}",
                details={
                    "unique_id": unique_id,
                    "project_slug": project_slug,
                    "rows_affected": result.get("rows_affected"),
                    "execution_time": result.get("execution_time"),
                },
            )
            LineageBus.publish(event)
            emitted += 1
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "could not emit dbt lineage for %s: %s", unique_id, exc
            )
    return emitted


__all__ = ["emit_dbt_run_lineage"]
