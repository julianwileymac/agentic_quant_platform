"""Dagster sensors that react to manifest changes."""
from __future__ import annotations

import json
from typing import Any

from dagster import (
    DagsterRunStatus,
    RunRequest,
    RunsFilter,
    SensorDefinition,
    SensorEvaluationContext,
    SkipReason,
    sensor,
)

from aqp.dagster.jobs import full_data_refresh_job

_ACTIVE_SENSOR_RUN_STATUSES = [
    DagsterRunStatus.NOT_STARTED,
    DagsterRunStatus.QUEUED,
    DagsterRunStatus.STARTED,
    DagsterRunStatus.CANCELING,
]
if hasattr(DagsterRunStatus, "STARTING"):
    _ACTIVE_SENSOR_RUN_STATUSES.append(DagsterRunStatus.STARTING)


def _decode_cursor(raw_cursor: str | None) -> dict[str, Any]:
    if not raw_cursor:
        return {}
    try:
        parsed = json.loads(raw_cursor)
        if isinstance(parsed, dict):
            return parsed
    except Exception:  # noqa: BLE001
        pass
    return {"fingerprint": str(raw_cursor)}


def _encode_cursor(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _manifest_fingerprint(row: Any) -> str:
    stamp = row.updated_at or row.created_at
    iso_stamp = stamp.isoformat() if stamp else "unknown"
    return f"{row.id}:{iso_stamp}"


def _has_active_duplicate_run(
    context: SensorEvaluationContext,
    *,
    manifest_id: int | str,
    manifest_fingerprint: str,
) -> bool:
    try:
        runs = context.instance.get_runs(
            filters=RunsFilter(
                job_name=full_data_refresh_job.name,
                statuses=_ACTIVE_SENSOR_RUN_STATUSES,
                tags={
                    "aqp.pipeline_manifest_id": str(manifest_id),
                    "aqp.pipeline_manifest_fingerprint": manifest_fingerprint,
                },
            ),
            limit=1,
        )
        return bool(runs)
    except Exception as exc:  # noqa: BLE001
        context.log.debug("manifest sensor duplicate-run guard unavailable: %s", exc)
        return False


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
        context.log.warning("manifest sensor unavailable: %s", exc)
        return SkipReason(f"manifest sensor unavailable: {exc}")

    if row is None:
        return SkipReason("no pipeline manifests discovered")

    cursor_payload = _decode_cursor(context.cursor)
    stamp = row.updated_at or row.created_at
    stamp_iso = stamp.isoformat() if stamp else "unknown"
    manifest_fingerprint = _manifest_fingerprint(row)
    if cursor_payload.get("fingerprint") == manifest_fingerprint:
        return SkipReason("latest pipeline manifest already processed")

    next_cursor = _encode_cursor(
        {
            "manifest_id": row.id,
            "manifest_name": row.name,
            "updated_at": stamp_iso,
            "fingerprint": manifest_fingerprint,
        }
    )

    if _has_active_duplicate_run(
        context,
        manifest_id=row.id,
        manifest_fingerprint=manifest_fingerprint,
    ):
        context.update_cursor(next_cursor)
        return SkipReason("active run already exists for latest pipeline manifest")

    context.update_cursor(next_cursor)
    yield RunRequest(
        run_key=manifest_fingerprint,
        run_config={},
        tags={
            "aqp.sensor": "pipeline_manifests_changed",
            "aqp.pipeline_manifest_id": str(row.id),
            "aqp.pipeline_manifest_name": str(row.name or ""),
            "aqp.pipeline_manifest_updated_at": stamp_iso,
            "aqp.pipeline_manifest_fingerprint": manifest_fingerprint,
        },
    )


ALL_SENSORS: list[SensorDefinition] = [pipeline_manifests_changed]


__all__ = ["ALL_SENSORS", "pipeline_manifests_changed"]
