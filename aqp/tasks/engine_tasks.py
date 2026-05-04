"""Celery tasks for declarative data-engine pipeline manifests."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select

from aqp.data.engine import Pipeline, PipelineManifest, build_executor
from aqp.persistence.db import get_session
from aqp.persistence.models_pipelines import PipelineManifestRow, PipelineRunRow
from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.engine_tasks.run_pipeline_manifest")
def run_pipeline_manifest(
    self,
    manifest_id: str,
    *,
    triggered_by: str | None = None,
) -> dict[str, Any]:
    """Execute a saved :class:`PipelineManifest` in the background."""
    task_id = self.request.id or "pipeline-manifest-run"
    emit(task_id, "start", "Loading pipeline manifest", manifest_id=manifest_id)
    run_id: str | None = None
    started = datetime.utcnow()
    try:
        with get_session() as session:
            manifest_row = session.execute(
                select(PipelineManifestRow).where(PipelineManifestRow.id == manifest_id).limit(1)
            ).scalar_one_or_none()
            if manifest_row is None:
                raise ValueError(f"manifest not found: {manifest_id}")
            spec = PipelineManifest.model_validate(manifest_row.spec_json or {})
            run_row = PipelineRunRow(
                manifest_id=manifest_row.id,
                namespace=spec.namespace,
                name=spec.name,
                backend=spec.compute.backend.value,
                status="running",
                triggered_by=triggered_by or "celery",
            )
            session.add(run_row)
            session.flush()
            run_id = run_row.id

        def _progress(stage: str, message: str, **extra: Any) -> None:
            emit(task_id, stage, message, manifest_id=manifest_id, run_id=run_id, **extra)

        pipeline = Pipeline.from_manifest(spec)
        executor = build_executor(spec, progress_cb=_progress)
        result = executor.execute(pipeline)
        finished = result.finished_at or datetime.utcnow()
        status = "ok" if not result.errors else "error"
        with get_session() as session:
            row = session.get(PipelineRunRow, run_id) if run_id else None
            if row is not None:
                row.status = status
                row.finished_at = finished
                row.rows_written = result.total_rows_written
                row.tables_written = len(result.tables)
                row.sink_result = dict(result.sink_result or {})
                row.lineage = dict(result.lineage or {})
                row.errors = list(result.errors)
                row.extras = list(result.extras)
                row.duration_seconds = (finished - started).total_seconds()
                session.add(row)
            manifest_row = session.get(PipelineManifestRow, manifest_id)
            if manifest_row is not None:
                manifest_row.last_run_at = finished
                manifest_row.last_run_status = status
                manifest_row.updated_at = finished
                session.add(manifest_row)

        payload = {
            "manifest_id": manifest_id,
            "run_id": run_id,
            "status": status,
            "result": result.to_dict(),
        }
        emit_done(task_id, payload)
        return payload
    except Exception as exc:
        logger.exception("run_pipeline_manifest failed")
        if run_id:
            with get_session() as session:
                row = session.get(PipelineRunRow, run_id)
                if row is not None:
                    row.status = "error"
                    row.finished_at = datetime.utcnow()
                    row.errors = [str(exc)]
                    session.add(row)
        emit_error(task_id, str(exc))
        raise


__all__ = ["run_pipeline_manifest"]
