"""``/bots`` — first-class Bot CRUD + lifecycle endpoints.

A :class:`aqp.bots.spec.BotSpec` is the smallest self-contained,
deployable unit on AQP. Each row in the ``bots`` table corresponds to
one named spec inside a project; ``bot_versions`` carries an immutable
hash-locked snapshot per change; ``bot_deployments`` ledgers every run
(backtest / paper / chat / k8s deploy).

Naming
------

Endpoints follow the existing tenancy-routes shape (see
:mod:`aqp.api.routes.projects`): mutations are async-session backed,
read-only listings drop into the same pattern, and lifecycle actions
hand off to Celery tasks under :mod:`aqp.tasks.bot_tasks`.

Streaming
---------

Async lifecycle actions return a :class:`aqp.api.schemas.TaskAccepted`
with ``stream_url`` pointing at the existing
``/chat/stream/{task_id}`` WebSocket — no new transport.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aqp.api.schemas import TaskAccepted
from aqp.bots.spec import BotSpec
from aqp.persistence import async_session_dep
from aqp.persistence.models_bots import Bot as BotRow
from aqp.persistence.models_bots import BotDeployment, BotVersion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bots", tags=["bots"])


# ----------------------------------------------------------------- schemas


class BotSummary(BaseModel):
    id: str
    name: str
    slug: str
    kind: str
    description: str | None = None
    status: str
    current_version: int
    project_id: str | None = None
    workspace_id: str | None = None
    annotations: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class BotDetail(BotSummary):
    spec: dict[str, Any] = Field(default_factory=dict)
    spec_yaml: str | None = None


class BotCreate(BaseModel):
    spec: dict[str, Any]
    project_id: str | None = None


class BotUpdate(BaseModel):
    spec: dict[str, Any] | None = None
    spec_yaml: str | None = None
    status: str | None = None
    description: str | None = None


class BotVersionOut(BaseModel):
    id: str
    bot_id: str
    version: int
    spec_hash: str
    created_at: datetime
    notes: str | None = None


class BotDeploymentOut(BaseModel):
    id: str
    bot_id: str | None
    version_id: str | None
    target: str
    status: str
    task_id: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    error: str | None = None
    result_summary: dict[str, Any] = Field(default_factory=dict)


class BotBacktestRequest(BaseModel):
    run_name: str | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)


class BotPaperRequest(BaseModel):
    run_name: str | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)


class BotDeployRequest(BaseModel):
    target: str | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)


class BotChatRequest(BaseModel):
    prompt: str
    session_id: str | None = None
    agent_role: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)


# ----------------------------------------------------------------- helpers


def _to_summary(row: BotRow) -> BotSummary:
    return BotSummary(
        id=row.id,
        name=row.name,
        slug=row.slug,
        kind=row.kind,
        description=row.description,
        status=row.status,
        current_version=int(row.current_version or 1),
        project_id=row.project_id,
        workspace_id=row.workspace_id,
        annotations=list(row.annotations or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_detail(row: BotRow) -> BotDetail:
    spec_payload: dict[str, Any] = {}
    if row.spec_yaml:
        try:
            spec_payload = BotSpec.from_yaml_str(row.spec_yaml).model_dump(mode="json")
        except Exception:
            spec_payload = {}
    return BotDetail(
        id=row.id,
        name=row.name,
        slug=row.slug,
        kind=row.kind,
        description=row.description,
        status=row.status,
        current_version=int(row.current_version or 1),
        project_id=row.project_id,
        workspace_id=row.workspace_id,
        annotations=list(row.annotations or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
        spec=spec_payload,
        spec_yaml=row.spec_yaml,
    )


async def _get_row(session: AsyncSession, bot_ref: str) -> BotRow:
    """Resolve a bot by id (UUID-ish) or slug, raise 404 if missing."""
    if len(bot_ref) == 36 and bot_ref.count("-") == 4:
        row = await session.get(BotRow, bot_ref)
        if row is not None:
            return row
    stmt = select(BotRow).where(BotRow.slug == bot_ref)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"bot {bot_ref!r} not found")
    return row


def _validate_spec_payload(payload: dict[str, Any]) -> BotSpec:
    try:
        return BotSpec.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"invalid bot spec: {exc}") from exc


# ----------------------------------------------------------------- CRUD


@router.get("", response_model=list[BotSummary])
async def list_bots(
    project_id: str | None = None,
    kind: str | None = None,
    status_filter: str | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(async_session_dep),
) -> list[BotSummary]:
    stmt = select(BotRow).order_by(BotRow.updated_at.desc()).limit(min(max(limit, 1), 500))
    if project_id:
        stmt = stmt.where(BotRow.project_id == project_id)
    if kind:
        stmt = stmt.where(BotRow.kind == kind)
    if status_filter:
        stmt = stmt.where(BotRow.status == status_filter)
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_summary(r) for r in rows]


@router.post("", response_model=BotDetail, status_code=status.HTTP_201_CREATED)
async def create_bot(
    body: BotCreate,
    session: AsyncSession = Depends(async_session_dep),
) -> BotDetail:
    spec = _validate_spec_payload(body.spec)
    if not spec.slug:
        raise HTTPException(status_code=422, detail="bot spec must have a non-empty slug")

    existing = (
        await session.execute(
            select(BotRow).where(
                BotRow.slug == spec.slug,
                BotRow.project_id == (body.project_id or BotRow.project_id),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"bot with slug {spec.slug!r} already exists in this project",
        )

    row = BotRow(
        name=spec.name,
        slug=spec.slug,
        kind=spec.kind,
        description=spec.description,
        status="draft",
        current_version=1,
        spec_yaml=spec.to_yaml(),
        annotations=spec.annotations,
    )
    if body.project_id:
        row.project_id = body.project_id
    session.add(row)
    await session.flush()

    version_row = BotVersion(
        bot_id=row.id,
        version=1,
        spec_hash=spec.snapshot_hash(),
        payload=spec.model_dump(mode="json"),
    )
    if body.project_id:
        version_row.project_id = body.project_id
    session.add(version_row)
    await session.commit()
    await session.refresh(row)
    return _to_detail(row)


@router.get("/{bot_ref}", response_model=BotDetail)
async def get_bot(
    bot_ref: str,
    session: AsyncSession = Depends(async_session_dep),
) -> BotDetail:
    row = await _get_row(session, bot_ref)
    return _to_detail(row)


@router.put("/{bot_ref}", response_model=BotDetail)
async def update_bot(
    bot_ref: str,
    body: BotUpdate,
    session: AsyncSession = Depends(async_session_dep),
) -> BotDetail:
    row = await _get_row(session, bot_ref)
    spec_dirty = False

    if body.spec is not None:
        spec = _validate_spec_payload(body.spec)
        row.name = spec.name
        row.kind = spec.kind
        row.description = spec.description
        row.spec_yaml = spec.to_yaml()
        row.annotations = spec.annotations
        spec_dirty = True
    elif body.spec_yaml is not None:
        try:
            spec = BotSpec.from_yaml_str(body.spec_yaml)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=f"invalid spec_yaml: {exc}") from exc
        row.name = spec.name
        row.kind = spec.kind
        row.description = spec.description
        row.spec_yaml = body.spec_yaml
        row.annotations = spec.annotations
        spec_dirty = True
    else:
        spec = None

    if body.status is not None:
        row.status = body.status
    if body.description is not None and not spec_dirty:
        row.description = body.description

    if spec is not None and spec_dirty:
        sha = spec.snapshot_hash()
        existing_version = (
            await session.execute(
                select(BotVersion).where(BotVersion.bot_id == row.id, BotVersion.spec_hash == sha)
            )
        ).scalar_one_or_none()
        if existing_version is None:
            next_version = int(row.current_version or 0) + 1
            version_row = BotVersion(
                bot_id=row.id,
                version=next_version,
                spec_hash=sha,
                payload=spec.model_dump(mode="json"),
            )
            if row.project_id:
                version_row.project_id = row.project_id
            session.add(version_row)
            row.current_version = next_version

    row.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(row)
    return _to_detail(row)


@router.delete(
    "/{bot_ref}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_bot(
    bot_ref: str,
    session: AsyncSession = Depends(async_session_dep),
) -> None:
    row = await _get_row(session, bot_ref)
    await session.delete(row)
    await session.commit()


# ----------------------------------------------------------------- versions


@router.get("/{bot_ref}/versions", response_model=list[BotVersionOut])
async def list_bot_versions(
    bot_ref: str,
    limit: int = 50,
    session: AsyncSession = Depends(async_session_dep),
) -> list[BotVersionOut]:
    row = await _get_row(session, bot_ref)
    stmt = (
        select(BotVersion)
        .where(BotVersion.bot_id == row.id)
        .order_by(desc(BotVersion.version))
        .limit(min(max(limit, 1), 500))
    )
    versions = (await session.execute(stmt)).scalars().all()
    return [
        BotVersionOut(
            id=v.id,
            bot_id=v.bot_id,
            version=v.version,
            spec_hash=v.spec_hash,
            created_at=v.created_at,
            notes=v.notes,
        )
        for v in versions
    ]


# ----------------------------------------------------------------- deployments


@router.get("/{bot_ref}/deployments", response_model=list[BotDeploymentOut])
async def list_bot_deployments(
    bot_ref: str,
    limit: int = 50,
    session: AsyncSession = Depends(async_session_dep),
) -> list[BotDeploymentOut]:
    row = await _get_row(session, bot_ref)
    stmt = (
        select(BotDeployment)
        .where(BotDeployment.bot_id == row.id)
        .order_by(desc(BotDeployment.started_at))
        .limit(min(max(limit, 1), 500))
    )
    deployments = (await session.execute(stmt)).scalars().all()
    return [
        BotDeploymentOut(
            id=d.id,
            bot_id=d.bot_id,
            version_id=d.version_id,
            target=d.target,
            status=d.status,
            task_id=d.task_id,
            started_at=d.started_at,
            ended_at=d.ended_at,
            error=d.error,
            result_summary=d.result_summary or {},
        )
        for d in deployments
    ]


# ----------------------------------------------------------------- lifecycle


@router.post("/{bot_ref}/backtest", response_model=TaskAccepted)
async def backtest_bot(
    bot_ref: str,
    body: BotBacktestRequest | None = None,
    session: AsyncSession = Depends(async_session_dep),
) -> TaskAccepted:
    row = await _get_row(session, bot_ref)
    body = body or BotBacktestRequest()
    from aqp.tasks.bot_tasks import run_bot_backtest

    handle = run_bot_backtest.delay(
        row.id,
        run_name=body.run_name,
        overrides=body.overrides,
    )
    return TaskAccepted(task_id=handle.id, stream_url=f"/chat/stream/{handle.id}")


@router.post("/{bot_ref}/paper/start", response_model=TaskAccepted)
async def start_bot_paper(
    bot_ref: str,
    body: BotPaperRequest | None = None,
    session: AsyncSession = Depends(async_session_dep),
) -> TaskAccepted:
    row = await _get_row(session, bot_ref)
    body = body or BotPaperRequest()
    from aqp.tasks.bot_tasks import run_bot_paper

    handle = run_bot_paper.delay(
        row.id,
        run_name=body.run_name,
        overrides=body.overrides,
    )
    return TaskAccepted(task_id=handle.id, stream_url=f"/chat/stream/{handle.id}")


@router.post("/{bot_ref}/paper/stop/{task_id}")
async def stop_bot_paper(bot_ref: str, task_id: str) -> dict[str, Any]:
    """Send a stop signal to an in-flight paper session.

    Reuses :func:`aqp.tasks.paper_tasks.publish_stop_signal` so existing
    paper-stop infrastructure (Redis pub/sub) covers bots transparently.
    """
    from aqp.tasks.paper_tasks import publish_stop_signal

    publish_stop_signal(task_id, reason=f"bot:{bot_ref}:manual")
    return {"task_id": task_id, "bot": bot_ref, "ok": True}


@router.post("/{bot_ref}/deploy", response_model=TaskAccepted)
async def deploy_bot_route(
    bot_ref: str,
    body: BotDeployRequest | None = None,
    session: AsyncSession = Depends(async_session_dep),
) -> TaskAccepted:
    row = await _get_row(session, bot_ref)
    body = body or BotDeployRequest()
    from aqp.tasks.bot_tasks import deploy_bot as deploy_task

    handle = deploy_task.delay(
        row.id,
        target=body.target,
        overrides=body.overrides,
    )
    return TaskAccepted(task_id=handle.id, stream_url=f"/chat/stream/{handle.id}")


@router.post("/{bot_ref}/chat", response_model=TaskAccepted)
async def chat_bot(
    bot_ref: str,
    body: BotChatRequest,
    session: AsyncSession = Depends(async_session_dep),
) -> TaskAccepted:
    """ResearchBot chat — dispatches a Celery task; consume via /chat/stream/{task_id}."""
    row = await _get_row(session, bot_ref)
    if row.kind != "research":
        raise HTTPException(
            status_code=400,
            detail=f"bot kind={row.kind!r} does not support chat (only 'research' bots do)",
        )
    from aqp.tasks.bot_tasks import chat_research_bot

    handle = chat_research_bot.delay(
        row.id,
        body.prompt,
        session_id=body.session_id,
        agent_role=body.agent_role,
        inputs=body.inputs,
    )
    return TaskAccepted(task_id=handle.id, stream_url=f"/chat/stream/{handle.id}")
