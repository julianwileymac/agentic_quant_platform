"""Dagster sensors that react to manifest changes."""
from __future__ import annotations

from typing import Any

from dagster import RunRequest, SensorDefinition, SensorEvaluationContext, sensor

from aqp.dagster.jobs import full_data_refresh_job


@sensor(
    job=full_data_refresh_job,
    name="pipeline_manifests_changed",
    minimum_interval_seconds=300,
    description="Trigger a full refresh when a new pipeline_manifests row appears.",
)
def pipeline_manifests_changed(context: SensorEvaluationContext) -> Any:
    try:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models_pipelines import PipelineManifestRow

        with get_session() as session:
            row = session.execute(
                select(PipelineManifestRow)
                .order_by(PipelineManifestRow.updated_at.desc())
                .limit(1)
            ).scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001
        context.log.debug("manifest sensor unavailable: %s", exc)
        return

    if row is None:
        return
    last_seen = context.cursor or ""
    cursor = (row.updated_at or row.created_at).isoformat()
    if cursor == last_seen:
        return
    context.update_cursor(cursor)
    yield RunRequest(run_key=cursor, run_config={})


ALL_SENSORS: list[SensorDefinition] = [pipeline_manifests_changed]


__all__ = ["ALL_SENSORS", "pipeline_manifests_changed"]
