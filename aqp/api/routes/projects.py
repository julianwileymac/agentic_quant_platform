"""``/projects`` — trading-bot project CRUD + Lean-style sub-resource lists.

Sub-resource endpoints mirror Lean's REST shape (``projects/{id}/...``)
so an existing Lean client can adapt with minimal route renames. See
``inspiration/Lean-master/Api/Api.cs`` for the canonical surface.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aqp.auth import CurrentUser, current_user
from aqp.persistence import async_session_dep
from aqp.persistence.models import (
    BacktestRun,
    ModelDeployment,
    Strategy,
)
from aqp.persistence.models_agents import AgentRunV2, AgentSpecRow
from aqp.persistence.models_data_control import DatasetPipelineConfigRow
from aqp.persistence.models_pipelines import PipelineManifestRow
from aqp.persistence.models_tenancy import Membership, Project

router = APIRouter(prefix="/projects", tags=["tenancy"])


class ProjectIn(BaseModel):
    workspace_id: str
    slug: str
    name: str
    description: str | None = None
    settings: dict[str, Any] | None = None


class ProjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    archived: bool | None = None
    settings: dict[str, Any] | None = None


class ProjectOut(BaseModel):
    id: str
    workspace_id: str
    slug: str
    name: str
    description: str | None = None
    archived: bool
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


def _to_proj(row: Project) -> ProjectOut:
    return ProjectOut(
        id=row.id,
        workspace_id=row.workspace_id,
        slug=row.slug,
        name=row.name,
        description=row.description,
        archived=row.archived,
        settings=row.settings or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    workspace_id: str | None = None,
    session: AsyncSession = Depends(async_session_dep),
) -> list[ProjectOut]:
    stmt = select(Project).order_by(Project.name)
    if workspace_id:
        stmt = stmt.where(Project.workspace_id == workspace_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_proj(r) for r in rows]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectIn,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(current_user),
) -> ProjectOut:
    row = Project(
        workspace_id=body.workspace_id,
        slug=body.slug,
        name=body.name,
        description=body.description,
        settings=body.settings or {},
    )
    session.add(row)
    await session.flush()
    session.add(
        Membership(
            user_id=user.id,
            scope_kind="project",
            scope_id=row.id,
            role="owner",
            live_control=True,
            granted_by=user.id,
        )
    )
    await session.commit()
    await session.refresh(row)
    return _to_proj(row)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> ProjectOut:
    row = await session.get(Project, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    return _to_proj(row)


@router.patch("/{project_id}", response_model=ProjectOut)
async def patch_project(
    project_id: str,
    body: ProjectPatch,
    session: AsyncSession = Depends(async_session_dep),
) -> ProjectOut:
    row = await session.get(Project, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(row)
    return _to_proj(row)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_project(
    project_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> None:
    row = await session.get(Project, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    await session.delete(row)
    await session.commit()


@router.get("/{project_id}/strategies")
async def list_project_strategies(
    project_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Strategy).where(Strategy.project_id == project_id).order_by(Strategy.name)
        )
    ).scalars().all()
    return [
        {"id": r.id, "name": r.name, "version": r.version, "status": r.status}
        for r in rows
    ]


@router.get("/{project_id}/backtests")
async def list_project_backtests(
    project_id: str,
    session: AsyncSession = Depends(async_session_dep),
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(BacktestRun)
            .where(BacktestRun.project_id == project_id)
            .order_by(BacktestRun.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "status": r.status,
            "sharpe": r.sharpe,
            "total_return": r.total_return,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/{project_id}/agents")
async def list_project_agents(
    project_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(AgentSpecRow)
            .where(AgentSpecRow.project_id == project_id)
            .order_by(AgentSpecRow.name)
        )
    ).scalars().all()
    return [
        {"id": r.id, "name": r.name, "role": r.role, "current_version": r.current_version}
        for r in rows
    ]


@router.get("/{project_id}/runs")
async def list_project_agent_runs(
    project_id: str,
    session: AsyncSession = Depends(async_session_dep),
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(AgentRunV2)
            .where(AgentRunV2.project_id == project_id)
            .order_by(AgentRunV2.started_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "spec_name": r.spec_name,
            "status": r.status,
            "cost_usd": r.cost_usd,
            "started_at": r.started_at,
        }
        for r in rows
    ]


@router.get("/{project_id}/deployments")
async def list_project_deployments(
    project_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(ModelDeployment)
            .where(ModelDeployment.project_id == project_id)
            .order_by(ModelDeployment.name)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "status": r.status,
            "alpha_class": r.alpha_class,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Project-level dataset configs and pipelines
# ---------------------------------------------------------------------------
class DatasetConfigIn(BaseModel):
    name: str
    config_json: dict[str, Any] = Field(default_factory=dict)
    sinks: list[str] = Field(default_factory=list)
    automations: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    status: str = "draft"
    is_active: bool = True
    manifest_id: str | None = None
    dataset_catalog_id: str | None = None


class DatasetConfigOut(BaseModel):
    id: str
    name: str
    version: int
    status: str
    config_json: dict[str, Any] = Field(default_factory=dict)
    sinks: list[Any] = Field(default_factory=list)
    automations: list[Any] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    is_active: bool
    manifest_id: str | None = None
    dataset_catalog_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def _to_config(row: DatasetPipelineConfigRow) -> DatasetConfigOut:
    return DatasetConfigOut(
        id=row.id,
        name=row.name,
        version=int(row.version or 1),
        status=row.status,
        config_json=dict(row.config_json or {}),
        sinks=list(row.sinks or []),
        automations=list(row.automations or []),
        tags=list(row.tags or []),
        notes=row.notes,
        is_active=bool(row.is_active),
        manifest_id=row.manifest_id,
        dataset_catalog_id=row.dataset_catalog_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/{project_id}/dataset-configs", response_model=list[DatasetConfigOut])
async def list_project_dataset_configs(
    project_id: str,
    session: AsyncSession = Depends(async_session_dep),
    active_only: bool = False,
    limit: int = 200,
) -> list[DatasetConfigOut]:
    stmt = (
        select(DatasetPipelineConfigRow)
        .where(DatasetPipelineConfigRow.project_id == project_id)
        .order_by(DatasetPipelineConfigRow.updated_at.desc())
        .limit(limit)
    )
    if active_only:
        stmt = stmt.where(DatasetPipelineConfigRow.is_active.is_(True))
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_config(r) for r in rows]


@router.post(
    "/{project_id}/dataset-configs",
    response_model=DatasetConfigOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_dataset_config(
    project_id: str,
    body: DatasetConfigIn,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(current_user),
) -> DatasetConfigOut:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    row = DatasetPipelineConfigRow(
        name=body.name,
        config_json=dict(body.config_json),
        sinks=list(body.sinks),
        automations=list(body.automations),
        tags=list(body.tags),
        notes=body.notes,
        status=body.status,
        is_active=body.is_active,
        manifest_id=body.manifest_id,
        dataset_catalog_id=body.dataset_catalog_id,
        created_by=user.id,
        owner_user_id=user.id,
        workspace_id=project.workspace_id,
        project_id=project.id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _to_config(row)


@router.patch("/{project_id}/dataset-configs/{config_id}", response_model=DatasetConfigOut)
async def patch_project_dataset_config(
    project_id: str,
    config_id: str,
    body: DatasetConfigIn,
    session: AsyncSession = Depends(async_session_dep),
) -> DatasetConfigOut:
    row = await session.get(DatasetPipelineConfigRow, config_id)
    if row is None or row.project_id != project_id:
        raise HTTPException(status_code=404, detail="config not found")
    row.name = body.name
    row.config_json = dict(body.config_json)
    row.sinks = list(body.sinks)
    row.automations = list(body.automations)
    row.tags = list(body.tags)
    row.notes = body.notes
    row.status = body.status
    row.is_active = body.is_active
    row.manifest_id = body.manifest_id
    row.dataset_catalog_id = body.dataset_catalog_id
    row.version = int(row.version or 1) + 1
    row.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(row)
    return _to_config(row)


@router.delete(
    "/{project_id}/dataset-configs/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_project_dataset_config(
    project_id: str,
    config_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> Response:
    row = await session.get(DatasetPipelineConfigRow, config_id)
    if row is None or row.project_id != project_id:
        raise HTTPException(status_code=404, detail="config not found")
    await session.delete(row)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}/pipelines")
async def list_project_pipelines(
    project_id: str,
    session: AsyncSession = Depends(async_session_dep),
    enabled_only: bool = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    stmt = (
        select(PipelineManifestRow)
        .where(PipelineManifestRow.project_id == project_id)
        .order_by(PipelineManifestRow.updated_at.desc())
        .limit(limit)
    )
    if enabled_only:
        stmt = stmt.where(PipelineManifestRow.enabled.is_(True))
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "namespace": r.namespace,
            "description": r.description,
            "owner": r.owner,
            "version": int(r.version or 1),
            "enabled": bool(r.enabled),
            "compute_backend": r.compute_backend,
            "schedule_cron": r.schedule_cron,
            "tags": list(r.tags or []),
            "last_run_at": r.last_run_at,
            "last_run_status": r.last_run_status,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]
