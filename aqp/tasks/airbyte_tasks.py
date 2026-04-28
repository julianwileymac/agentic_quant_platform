"""Celery tasks for Airbyte sync orchestration and embedded dry-runs."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aqp.data.airbyte.models import AirbyteEmbeddedReadRequest, AirbyteSyncRequest
from aqp.services.airbyte_client import AirbyteClient, extract_job_id, normalize_job_status
from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.airbyte_tasks.discover_airbyte_source")
def discover_airbyte_source(self, payload: dict[str, Any]) -> dict[str, Any]:
    """Discover source streams through the embedded runner by default."""
    task_id = self.request.id or "airbyte-discover"
    emit(task_id, "start", "Discovering Airbyte source streams")
    try:
        from aqp.data.airbyte.embedded import EmbeddedAirbyteRunner

        connector_id = str(payload.get("connector_id") or "")
        config = dict(payload.get("config") or {})
        dry_run = bool(payload.get("dry_run", True))
        result = EmbeddedAirbyteRunner().discover(connector_id, config, dry_run=dry_run)
        emit_done(task_id, result)
        return result
    except Exception as exc:
        logger.exception("discover_airbyte_source failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.airbyte_tasks.run_embedded_airbyte_read")
def run_embedded_airbyte_read(self, payload: dict[str, Any]) -> dict[str, Any]:
    """Run an embedded PyAirbyte-style read, usually in dry-run mode."""
    task_id = self.request.id or "airbyte-embedded"
    emit(task_id, "start", "Running embedded Airbyte read")
    try:
        from aqp.data.airbyte.embedded import EmbeddedAirbyteRunner

        request = AirbyteEmbeddedReadRequest.model_validate(payload)
        result = EmbeddedAirbyteRunner().read(request)
        emit_done(task_id, result)
        return result
    except Exception as exc:
        logger.exception("run_embedded_airbyte_read failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.airbyte_tasks.sync_airbyte_connection")
def sync_airbyte_connection(self, payload: dict[str, Any]) -> dict[str, Any]:
    """Trigger an Airbyte connection sync and optionally wait for completion."""
    task_id = self.request.id or "airbyte-sync"
    emit(task_id, "start", "Starting Airbyte connection sync")
    run_id: str | None = None
    try:
        request = AirbyteSyncRequest.model_validate(payload)
        connection = _resolve_connection_payload(request)
        airbyte_connection_id = connection.get("airbyte_connection_id")
        if not airbyte_connection_id:
            raise ValueError("airbyte_connection_id is required for production sync")

        run_id = _create_run_row(
            task_id=task_id,
            connection_id=connection.get("id"),
            airbyte_connection_id=airbyte_connection_id,
            runtime="full_airbyte",
            payload=payload,
        )

        client = AirbyteClient()
        job = client.trigger_sync(airbyte_connection_id)
        job_id = extract_job_id(job)
        emit(
            task_id,
            "queued",
            f"Airbyte sync queued for connection {airbyte_connection_id}",
            airbyte_job_id=job_id,
        )
        _update_run_row(run_id, airbyte_job_id=job_id, status="running", payload=job)

        final_payload = job
        if request.wait and job_id:
            final_payload = client.wait_for_job(
                job_id,
                poll_interval_seconds=request.poll_interval_seconds,
                timeout_seconds=request.timeout_seconds,
            )
        status = normalize_job_status(final_payload).value
        response = {
            "run_id": run_id,
            "connection_id": connection.get("id"),
            "airbyte_connection_id": airbyte_connection_id,
            "airbyte_job_id": job_id,
            "status": status,
            "payload": final_payload,
        }

        if request.materialize_after_sync and connection.get("materialization_manifest"):
            emit(task_id, "materializing", "Running post-sync AQP materialization")
            response["materialization"] = _run_materialization(
                connection["materialization_manifest"]
            )

        _finish_run_row(run_id, status=status, payload=response)
        emit_done(task_id, response)
        return response
    except Exception as exc:
        logger.exception("sync_airbyte_connection failed")
        if run_id:
            _finish_run_row(run_id, status="failed", error=str(exc))
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.airbyte_tasks.materialize_airbyte_staging")
def materialize_airbyte_staging(self, manifest: dict[str, Any]) -> dict[str, Any]:
    """Run an AQP PipelineManifest against Airbyte-staged data."""
    task_id = self.request.id or "airbyte-materialize"
    emit(task_id, "start", "Materializing Airbyte staging through AQP engine")
    try:
        result = _run_materialization(manifest)
        emit_done(task_id, result)
        return result
    except Exception as exc:
        logger.exception("materialize_airbyte_staging failed")
        emit_error(task_id, str(exc))
        raise


def _resolve_connection_payload(request: AirbyteSyncRequest) -> dict[str, Any]:
    if request.spec:
        data = request.spec.model_dump(mode="json")
        data["id"] = request.spec.id
        return data
    if not request.connection_id:
        raise ValueError("connection_id or spec is required")

    from sqlalchemy import select

    from aqp.persistence.db import get_session
    from aqp.persistence.models_airbyte import AirbyteConnectionRow

    with get_session() as session:
        row = session.execute(
            select(AirbyteConnectionRow).where(AirbyteConnectionRow.id == request.connection_id)
        ).scalar_one_or_none()
        if row is None:
            raise ValueError(f"Airbyte connection not found: {request.connection_id}")
        return {
            "id": row.id,
            "name": row.name,
            "airbyte_connection_id": row.airbyte_connection_id,
            "materialization_manifest": row.materialization_manifest,
        }


def _run_materialization(manifest: dict[str, Any]) -> dict[str, Any]:
    from aqp.data.engine import Pipeline, PipelineManifest, build_executor

    spec = PipelineManifest.model_validate(manifest)
    pipeline = Pipeline.from_manifest(spec)
    executor = build_executor(spec)
    return executor.execute(pipeline).to_dict()


def _create_run_row(
    *,
    task_id: str,
    connection_id: str | None,
    airbyte_connection_id: str | None,
    runtime: str,
    payload: dict[str, Any],
) -> str | None:
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_airbyte import AirbyteSyncRunRow

        with get_session() as session:
            row = AirbyteSyncRunRow(
                connection_id=connection_id,
                task_id=task_id,
                airbyte_connection_id=airbyte_connection_id,
                runtime=runtime,
                status="running",
                payload=payload,
            )
            session.add(row)
            session.flush()
            return row.id
    except Exception:
        logger.debug("Airbyte run row creation skipped", exc_info=True)
        return None


def _update_run_row(run_id: str | None, **updates: Any) -> None:
    if not run_id:
        return
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_airbyte import AirbyteSyncRunRow

        with get_session() as session:
            row = session.get(AirbyteSyncRunRow, run_id)
            if row is None:
                return
            for key, value in updates.items():
                setattr(row, key, value)
            session.add(row)
    except Exception:
        logger.debug("Airbyte run row update skipped", exc_info=True)


def _finish_run_row(
    run_id: str | None,
    *,
    status: str,
    payload: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    if not run_id:
        return
    finished_at = datetime.utcnow()
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_airbyte import AirbyteSyncRunRow

        with get_session() as session:
            row = session.get(AirbyteSyncRunRow, run_id)
            if row is None:
                return
            row.status = status
            row.finished_at = finished_at
            if row.started_at:
                row.duration_seconds = (finished_at - row.started_at).total_seconds()
            if payload is not None:
                row.payload = payload
            if error is not None:
                row.error = error
            session.add(row)
    except Exception:
        logger.debug("Airbyte run row finish skipped", exc_info=True)


__all__ = [
    "discover_airbyte_source",
    "materialize_airbyte_staging",
    "run_embedded_airbyte_read",
    "sync_airbyte_connection",
]
