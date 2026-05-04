"""Pipeline manifest CRUD + run endpoints."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.schemas import TaskAccepted
from aqp.data.engine import (
    Pipeline,
    PipelineManifest,
    build_executor,
)
from aqp.persistence.db import get_session
from aqp.persistence.models_pipelines import (
    PipelineManifestRow,
    PipelineRunRow,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/engine", tags=["data-engine"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ManifestSummary(BaseModel):
    id: str
    name: str
    namespace: str
    description: str | None = None
    owner: str | None = None
    version: int = 1
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    compute_backend: str | None = None
    schedule_cron: str | None = None
    last_run_at: datetime | None = None
    last_run_status: str | None = None


class ManifestPayload(BaseModel):
    spec: PipelineManifest
    owner: str | None = None
    enabled: bool | None = None


class RunSummary(BaseModel):
    id: str
    manifest_id: str | None = None
    namespace: str
    name: str
    backend: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    rows_written: int = 0
    tables_written: int = 0
    triggered_by: str | None = None
    duration_seconds: float | None = None


# ---------------------------------------------------------------------------
# Manifest CRUD
# ---------------------------------------------------------------------------


@router.get("/manifests", response_model=list[ManifestSummary])
def list_manifests(
    namespace: str | None = Query(default=None),
    enabled_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = select(PipelineManifestRow)
        if namespace:
            stmt = stmt.where(PipelineManifestRow.namespace == namespace)
        if enabled_only:
            stmt = stmt.where(PipelineManifestRow.enabled.is_(True))
        rows = session.execute(stmt.order_by(PipelineManifestRow.name).limit(limit)).scalars().all()
        return [_manifest_summary(row) for row in rows]


@router.post("/manifests", response_model=ManifestSummary)
def create_manifest(payload: ManifestPayload) -> dict[str, Any]:
    spec = payload.spec
    with get_session() as session:
        existing = session.execute(
            select(PipelineManifestRow)
            .where(PipelineManifestRow.namespace == spec.namespace)
            .where(PipelineManifestRow.name == spec.name)
            .limit(1)
        ).scalar_one_or_none()
        spec_json = spec.model_dump(mode="json")
        if existing is None:
            row = PipelineManifestRow(
                name=spec.name,
                namespace=spec.namespace,
                description=spec.description,
                owner=payload.owner or spec.owner,
                version=int(spec.version or 1),
                enabled=(
                    bool(payload.enabled) if payload.enabled is not None else spec.enabled
                ),
                spec_json=spec_json,
                tags=list(spec.tags),
                compute_backend=spec.compute.backend.value,
                schedule_cron=spec.schedule.cron,
            )
            session.add(row)
            session.flush()
            return _manifest_summary(row)
        existing.description = spec.description or existing.description
        existing.owner = payload.owner or spec.owner or existing.owner
        existing.version = int((spec.version or existing.version) or 1)
        if payload.enabled is not None:
            existing.enabled = bool(payload.enabled)
        existing.spec_json = spec_json
        existing.tags = list(spec.tags)
        existing.compute_backend = spec.compute.backend.value
        existing.schedule_cron = spec.schedule.cron
        existing.updated_at = datetime.utcnow()
        session.add(existing)
        return _manifest_summary(existing)


@router.get("/manifests/{manifest_id}")
def get_manifest(manifest_id: str) -> dict[str, Any]:
    with get_session() as session:
        row = session.execute(
            select(PipelineManifestRow)
            .where(PipelineManifestRow.id == manifest_id)
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="manifest not found")
        return {
            **_manifest_summary(row),
            "spec": row.spec_json,
            "created_at": (row.created_at or datetime.utcnow()).isoformat(),
            "updated_at": (row.updated_at or datetime.utcnow()).isoformat(),
        }


@router.delete("/manifests/{manifest_id}")
def delete_manifest(manifest_id: str) -> dict[str, Any]:
    with get_session() as session:
        row = session.execute(
            select(PipelineManifestRow)
            .where(PipelineManifestRow.id == manifest_id)
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="manifest not found")
        session.delete(row)
        return {"id": manifest_id, "status": "deleted"}


# ---------------------------------------------------------------------------
# Run + status
# ---------------------------------------------------------------------------


@router.post("/manifests/{manifest_id}/run")
def run_manifest(manifest_id: str, triggered_by: str | None = Query(default=None)) -> dict[str, Any]:
    with get_session() as session:
        manifest_row = session.execute(
            select(PipelineManifestRow)
            .where(PipelineManifestRow.id == manifest_id)
            .limit(1)
        ).scalar_one_or_none()
        if manifest_row is None:
            raise HTTPException(status_code=404, detail="manifest not found")
        spec = PipelineManifest.model_validate(manifest_row.spec_json or {})

        run_row = PipelineRunRow(
            manifest_id=manifest_row.id,
            namespace=spec.namespace,
            name=spec.name,
            backend=spec.compute.backend.value,
            status="running",
            triggered_by=triggered_by or "api",
        )
        session.add(run_row)
        session.flush()
        run_id = run_row.id

    started = datetime.utcnow()
    try:
        pipeline = Pipeline.from_manifest(spec)
        executor = build_executor(spec)
        result = executor.execute(pipeline)
    except Exception as exc:  # noqa: BLE001
        logger.exception("manifest run failed")
        with get_session() as session:
            row = session.get(PipelineRunRow, run_id)
            if row is not None:
                row.status = "error"
                row.finished_at = datetime.utcnow()
                row.errors = [str(exc)]
                session.add(row)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    finished = result.finished_at or datetime.utcnow()
    with get_session() as session:
        row = session.get(PipelineRunRow, run_id)
        if row is not None:
            row.status = "ok" if not result.errors else "error"
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
            manifest_row.last_run_status = (
                "ok" if not result.errors else "error"
            )
            session.add(manifest_row)
    return {
        "manifest_id": manifest_id,
        "run_id": run_id,
        "status": "ok" if not result.errors else "error",
        "result": result.to_dict(),
    }


@router.post("/manifests/{manifest_id}/run-background", response_model=TaskAccepted)
def queue_manifest_run(
    manifest_id: str,
    triggered_by: str | None = Query(default=None),
) -> TaskAccepted:
    """Queue a saved manifest run on the ingestion worker."""
    with get_session() as session:
        row = session.execute(
            select(PipelineManifestRow).where(PipelineManifestRow.id == manifest_id).limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="manifest not found")

    from aqp.tasks.engine_tasks import run_pipeline_manifest

    async_result = run_pipeline_manifest.delay(manifest_id, triggered_by=triggered_by or "api")
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.post("/run-adhoc")
def run_adhoc(spec: PipelineManifest) -> dict[str, Any]:
    """Run a manifest without persisting it (sandbox flow)."""
    pipeline = Pipeline.from_manifest(spec)
    executor = build_executor(spec)
    result = executor.execute(pipeline)
    return {"status": "ok" if not result.errors else "error", "result": result.to_dict()}


@router.get("/runs", response_model=list[RunSummary])
def list_runs(
    manifest_id: str | None = Query(default=None),
    namespace: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = select(PipelineRunRow).order_by(desc(PipelineRunRow.started_at)).limit(limit)
        if manifest_id:
            stmt = stmt.where(PipelineRunRow.manifest_id == manifest_id)
        if namespace:
            stmt = stmt.where(PipelineRunRow.namespace == namespace)
        if status:
            stmt = stmt.where(PipelineRunRow.status == status)
        rows = session.execute(stmt).scalars().all()
        return [_run_summary(row) for row in rows]


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    with get_session() as session:
        row = session.execute(
            select(PipelineRunRow).where(PipelineRunRow.id == run_id).limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {
            **_run_summary(row),
            "sink_result": dict(row.sink_result or {}),
            "lineage": dict(row.lineage or {}),
            "errors": list(row.errors or []),
            "extras": list(row.extras or []),
            "code_version_sha": row.code_version_sha,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _manifest_summary(row: PipelineManifestRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "namespace": row.namespace,
        "description": row.description,
        "owner": row.owner,
        "version": int(row.version or 1),
        "enabled": bool(row.enabled),
        "tags": list(row.tags or []),
        "compute_backend": row.compute_backend,
        "schedule_cron": row.schedule_cron,
        "last_run_at": row.last_run_at,
        "last_run_status": row.last_run_status,
    }


def _run_summary(row: PipelineRunRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "manifest_id": row.manifest_id,
        "namespace": row.namespace,
        "name": row.name,
        "backend": row.backend,
        "status": row.status,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "rows_written": int(row.rows_written or 0),
        "tables_written": int(row.tables_written or 0),
        "triggered_by": row.triggered_by,
        "duration_seconds": row.duration_seconds,
    }
