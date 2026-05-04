"""Aggregated data-layer control plane endpoints."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from aqp.api.schemas import TaskAccepted
from aqp.persistence.db import get_session
from aqp.persistence.models import DataSource, DatasetCatalog, DatasetVersion
from aqp.persistence.models_airbyte import AirbyteConnectionRow, AirbyteSyncRunRow
from aqp.persistence.models_data_control import DatasetPipelineConfigRow, SourceLibraryEntry
from aqp.persistence.models_pipelines import PipelineManifestRow, PipelineRunRow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/data-control", tags=["data-control"])


MetadataTarget = Literal["airbyte", "dagster", "dbt"]


class MetadataSyncRequest(BaseModel):
    targets: list[MetadataTarget] = Field(default_factory=lambda: ["airbyte", "dagster", "dbt"])
    enrich_with_llm: bool = False
    discover_airbyte_schemas: bool = True


class PipelineConfigRequest(BaseModel):
    name: str
    dataset_catalog_id: str | None = None
    manifest_id: str | None = None
    status: str = "draft"
    config_json: dict[str, Any] = Field(default_factory=dict)
    sinks: list[str] = Field(default_factory=list)
    automations: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    created_by: str = "api"


class PipelineConfigView(PipelineConfigRequest):
    id: str
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


@router.get("/summary")
def summary() -> dict[str, Any]:
    """Return one compact snapshot for the Data Pipelines control page."""
    try:
        with get_session() as session:
            counts = {
                "data_sources": _count(session, DataSource),
                "dataset_catalogs": _count(session, DatasetCatalog),
                "dataset_versions": _count(session, DatasetVersion),
                "pipeline_manifests": _count(session, PipelineManifestRow),
                "pipeline_runs": _count(session, PipelineRunRow),
                "airbyte_connections": _count(session, AirbyteConnectionRow),
                "airbyte_runs": _count(session, AirbyteSyncRunRow),
                "source_library_entries": _count(session, SourceLibraryEntry),
                "dataset_pipeline_configs": _count(session, DatasetPipelineConfigRow),
            }
            runs = session.execute(
                select(PipelineRunRow).order_by(desc(PipelineRunRow.started_at)).limit(10)
            ).scalars().all()
            scheduled = session.execute(
                select(PipelineManifestRow)
                .where(PipelineManifestRow.schedule_cron.is_not(None))
                .order_by(PipelineManifestRow.name)
                .limit(50)
            ).scalars().all()
            return {
                "counts": counts,
                "recent_runs": [_run_summary(row) for row in runs],
                "scheduled_manifests": [_manifest_summary(row) for row in scheduled],
                "metadata_sync": {
                    "last_checked_at": datetime.utcnow().isoformat(),
                    "airbyte_metadata_only": True,
                    "dagster_graphql": True,
                    "dbt_artifacts": True,
                },
            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("data-control summary degraded", exc_info=True)
        return {
            "counts": {},
            "recent_runs": [],
            "scheduled_manifests": [],
            "metadata_sync": {"error": str(exc)},
        }


@router.post("/metadata/sync", response_model=TaskAccepted)
def sync_metadata(req: MetadataSyncRequest) -> TaskAccepted:
    """Queue metadata-only sync across Airbyte, Dagster, and dbt."""
    from aqp.tasks.data_metadata_tasks import sync_data_metadata

    payload = req.model_dump(mode="json")
    async_result = sync_data_metadata.delay(payload)
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.get("/pipeline-configs", response_model=list[PipelineConfigView])
def list_pipeline_configs(active_only: bool = True, limit: int = 200) -> list[PipelineConfigView]:
    with get_session() as session:
        stmt = select(DatasetPipelineConfigRow).order_by(desc(DatasetPipelineConfigRow.created_at)).limit(limit)
        if active_only:
            stmt = stmt.where(DatasetPipelineConfigRow.is_active.is_(True))
        return [_pipeline_config_view(row) for row in session.execute(stmt).scalars().all()]


@router.post("/pipeline-configs", response_model=PipelineConfigView)
def create_pipeline_config(req: PipelineConfigRequest) -> PipelineConfigView:
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    with get_session() as session:
        current_version = (
            session.execute(
                select(func.max(DatasetPipelineConfigRow.version)).where(DatasetPipelineConfigRow.name == name)
            ).scalar_one()
            or 0
        )
        session.query(DatasetPipelineConfigRow).filter(
            DatasetPipelineConfigRow.name == name,
            DatasetPipelineConfigRow.is_active.is_(True),
        ).update({"is_active": False, "updated_at": datetime.utcnow()})
        row = DatasetPipelineConfigRow(
            name=name,
            dataset_catalog_id=req.dataset_catalog_id,
            manifest_id=req.manifest_id,
            version=int(current_version) + 1,
            status=req.status,
            config_json=dict(req.config_json or {}),
            sinks=list(req.sinks or []),
            automations=[dict(item) for item in (req.automations or [])],
            tags=list(req.tags or []),
            notes=req.notes,
            is_active=True,
            created_by=req.created_by,
        )
        session.add(row)
        session.flush()
        return _pipeline_config_view(row)


def _count(session: Any, model: type) -> int:
    return int(session.execute(select(func.count()).select_from(model)).scalar_one() or 0)


def _run_summary(row: PipelineRunRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "manifest_id": row.manifest_id,
        "namespace": row.namespace,
        "name": row.name,
        "backend": row.backend,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "rows_written": int(row.rows_written or 0),
        "tables_written": int(row.tables_written or 0),
        "triggered_by": row.triggered_by,
    }


def _manifest_summary(row: PipelineManifestRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "namespace": row.namespace,
        "description": row.description,
        "enabled": bool(row.enabled),
        "tags": list(row.tags or []),
        "compute_backend": row.compute_backend,
        "schedule_cron": row.schedule_cron,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "last_run_status": row.last_run_status,
    }


def _pipeline_config_view(row: DatasetPipelineConfigRow) -> PipelineConfigView:
    return PipelineConfigView(
        id=row.id,
        name=row.name,
        dataset_catalog_id=row.dataset_catalog_id,
        manifest_id=row.manifest_id,
        version=int(row.version or 1),
        status=row.status,
        config_json=dict(row.config_json or {}),
        sinks=list(row.sinks or []),
        automations=[dict(item) for item in (row.automations or [])],
        tags=list(row.tags or []),
        notes=row.notes,
        created_by=row.created_by,
        is_active=bool(row.is_active),
        created_at=row.created_at or datetime.utcnow(),
        updated_at=row.updated_at or datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# Automations + scheduling
# ---------------------------------------------------------------------------
class AutomationView(BaseModel):
    kind: str  # cron | manifest | preset_config | dagster_schedule
    name: str
    cron: str | None = None
    enabled: bool = True
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScheduleUpsertRequest(BaseModel):
    target_kind: Literal["pipeline_manifest", "dataset_pipeline_config"]
    target_id: str
    cron: str | None = None
    enabled: bool = True


class ScheduleUpsertResponse(BaseModel):
    target_kind: str
    target_id: str
    cron: str | None
    enabled: bool
    message: str = ""


@router.get("/automations", response_model=list[AutomationView])
def list_automations(limit: int = 200) -> list[AutomationView]:
    """Aggregate cron-driven automations across pipelines + dataset configs."""
    out: list[AutomationView] = []
    try:
        with get_session() as session:
            manifests = session.execute(
                select(PipelineManifestRow)
                .where(PipelineManifestRow.schedule_cron.is_not(None))
                .order_by(PipelineManifestRow.name)
                .limit(limit)
            ).scalars().all()
            for m in manifests:
                out.append(
                    AutomationView(
                        kind="pipeline_manifest",
                        name=m.name,
                        cron=m.schedule_cron,
                        enabled=bool(m.enabled),
                        last_run_at=m.last_run_at,
                        last_run_status=m.last_run_status,
                        metadata={
                            "id": m.id,
                            "namespace": m.namespace,
                            "tags": list(m.tags or []),
                        },
                    )
                )
            configs = session.execute(
                select(DatasetPipelineConfigRow)
                .where(DatasetPipelineConfigRow.is_active.is_(True))
                .limit(limit)
            ).scalars().all()
            for cfg in configs:
                for entry in cfg.automations or []:
                    cron = entry.get("cron") if isinstance(entry, dict) else None
                    if not cron:
                        continue
                    out.append(
                        AutomationView(
                            kind="dataset_pipeline_config",
                            name=cfg.name,
                            cron=cron,
                            enabled=bool(cfg.is_active),
                            metadata={
                                "id": cfg.id,
                                "tags": list(cfg.tags or []),
                                "preset": (cfg.config_json or {}).get("preset"),
                            },
                        )
                    )
    except Exception as exc:  # noqa: BLE001
        logger.debug("automations enumeration degraded", exc_info=True)
        return []
    return out


@router.post("/schedules", response_model=ScheduleUpsertResponse)
def upsert_schedule(req: ScheduleUpsertRequest) -> ScheduleUpsertResponse:
    """Patch the cron of a pipeline manifest or dataset pipeline config.

    The Celery beat scheduler in
    :mod:`aqp.tasks.scheduling` re-reads the active schedule on next
    tick (or on app start), so no separate restart is required.
    """
    with get_session() as session:
        if req.target_kind == "pipeline_manifest":
            row = session.get(PipelineManifestRow, req.target_id)
            if row is None:
                raise HTTPException(status_code=404, detail="manifest not found")
            row.schedule_cron = req.cron
            row.enabled = bool(req.enabled)
            row.updated_at = datetime.utcnow()
            session.add(row)
            session.commit()
            _refresh_beat_schedule_safely()
            return ScheduleUpsertResponse(
                target_kind=req.target_kind,
                target_id=req.target_id,
                cron=req.cron,
                enabled=row.enabled,
                message="manifest schedule updated",
            )
        if req.target_kind == "dataset_pipeline_config":
            row = session.get(DatasetPipelineConfigRow, req.target_id)
            if row is None:
                raise HTTPException(status_code=404, detail="config not found")
            existing = list(row.automations or [])
            cron_idx = next(
                (i for i, e in enumerate(existing) if isinstance(e, dict) and e.get("kind") == "cron"),
                None,
            )
            if req.cron:
                entry = {"kind": "cron", "cron": req.cron, "enabled": req.enabled}
                if cron_idx is None:
                    existing.append(entry)
                else:
                    existing[cron_idx] = entry
            elif cron_idx is not None:
                existing.pop(cron_idx)
            row.automations = existing
            row.is_active = bool(req.enabled)
            row.updated_at = datetime.utcnow()
            session.add(row)
            session.commit()
            _refresh_beat_schedule_safely()
            return ScheduleUpsertResponse(
                target_kind=req.target_kind,
                target_id=req.target_id,
                cron=req.cron,
                enabled=row.is_active,
                message="dataset config schedule updated",
            )
    raise HTTPException(status_code=400, detail=f"unsupported target_kind {req.target_kind}")


def _refresh_beat_schedule_safely() -> None:
    try:
        from aqp.tasks.scheduling import refresh_celery_beat_schedule

        refresh_celery_beat_schedule()
    except Exception:  # pragma: no cover
        logger.debug("beat schedule refresh skipped", exc_info=True)


__all__ = ["router"]
