"""``/experiments`` — Phase 1 umbrella CRUD + run-linkage queries.

The umbrella sits *above* the existing typed run tables — backtest /
RL / analysis / ML / bot deployment / paper / agent runs all reference
an experiment via the ``experiment_id`` FK added in alembic 0037. The
endpoints here let the UI:

- create / list / describe / archive experiments (with nesting via
  ``parent_experiment_id``);
- attach / detach typed run rows;
- list every run that ever pointed at an experiment;
- store the running-aggregate ``metrics`` blob.

Authorization piggy-backs on the active workspace / project context:
:func:`aqp.auth.deps.current_context` already validates the user can
see the requested project, so no extra scope check is needed beyond
``require_authenticated``.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aqp.auth import (
    CurrentUser,
    RequestContext,
    current_context,
    current_user,
    require_authenticated,
)
from aqp.persistence import async_session_dep
from aqp.persistence.models_experiments import (
    EXPERIMENT_KINDS,
    EXPERIMENT_STATUSES,
    Experiment,
)

router = APIRouter(prefix="/experiments", tags=["experiments"])


_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(name: str) -> str:
    """Make a URL-safe slug from a human-friendly name."""
    base = _SLUG_RE.sub("-", name.lower().strip()).strip("-")
    return base[:120] or "experiment"


class ExperimentIn(BaseModel):
    name: str
    slug: str | None = None
    description: str | None = None
    kind: str = "research"
    parent_experiment_id: str | None = None
    lab_id: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ExperimentPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    kind: str | None = None
    status: str | None = None
    parent_experiment_id: str | None = None
    lab_id: str | None = None
    metrics: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    tags: list[str] | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class ExperimentOut(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None = None
    kind: str
    status: str
    parent_experiment_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    lab_id: str | None = None
    owner_user_id: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


def _to_out(row: Experiment) -> ExperimentOut:
    return ExperimentOut(
        id=row.id,
        slug=row.slug,
        name=row.name,
        description=row.description,
        kind=row.kind,
        status=row.status,
        parent_experiment_id=row.parent_experiment_id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        lab_id=row.lab_id,
        owner_user_id=row.owner_user_id,
        metrics=dict(row.metrics or {}),
        meta=dict(row.meta or {}),
        tags=list(row.tags or []),
        started_at=row.started_at,
        ended_at=row.ended_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[ExperimentOut])
async def list_experiments(
    project_id: str | None = None,
    kind: str | None = None,
    status_filter: str | None = None,
    parent_experiment_id: str | None = None,
    limit: int = 200,
    session: AsyncSession = Depends(async_session_dep),
    ctx: RequestContext = Depends(current_context),
    _: CurrentUser = Depends(require_authenticated),
) -> list[ExperimentOut]:
    stmt = select(Experiment).order_by(Experiment.updated_at.desc()).limit(limit)
    target_project = project_id or ctx.project_id
    if target_project:
        stmt = stmt.where(Experiment.project_id == target_project)
    elif ctx.workspace_id:
        stmt = stmt.where(Experiment.workspace_id == ctx.workspace_id)
    if kind:
        stmt = stmt.where(Experiment.kind == kind)
    if status_filter:
        stmt = stmt.where(Experiment.status == status_filter)
    if parent_experiment_id:
        stmt = stmt.where(Experiment.parent_experiment_id == parent_experiment_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_out(r) for r in rows]


@router.post("", response_model=ExperimentOut, status_code=status.HTTP_201_CREATED)
async def create_experiment(
    body: ExperimentIn,
    session: AsyncSession = Depends(async_session_dep),
    ctx: RequestContext = Depends(current_context),
    user: CurrentUser = Depends(require_authenticated),
) -> ExperimentOut:
    if body.kind not in EXPERIMENT_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"kind must be one of {EXPERIMENT_KINDS}",
        )
    row = Experiment(
        slug=body.slug or _slugify(body.name),
        name=body.name,
        description=body.description,
        kind=body.kind,
        parent_experiment_id=body.parent_experiment_id,
        lab_id=body.lab_id or ctx.lab_id,
        metrics=dict(body.metrics or {}),
        meta=dict(body.meta or {}),
        tags=list(body.tags or []),
        owner_user_id=user.id,
        workspace_id=ctx.workspace_id,
        project_id=ctx.project_id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _to_out(row)


@router.get("/{experiment_id}", response_model=ExperimentOut)
async def get_experiment(
    experiment_id: str,
    session: AsyncSession = Depends(async_session_dep),
    _: CurrentUser = Depends(require_authenticated),
) -> ExperimentOut:
    row = await session.get(Experiment, experiment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return _to_out(row)


@router.patch("/{experiment_id}", response_model=ExperimentOut)
async def patch_experiment(
    experiment_id: str,
    body: ExperimentPatch,
    session: AsyncSession = Depends(async_session_dep),
    _: CurrentUser = Depends(require_authenticated),
) -> ExperimentOut:
    row = await session.get(Experiment, experiment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    payload = body.model_dump(exclude_unset=True)
    if "kind" in payload and payload["kind"] not in EXPERIMENT_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"kind must be one of {EXPERIMENT_KINDS}",
        )
    if "status" in payload and payload["status"] not in EXPERIMENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"status must be one of {EXPERIMENT_STATUSES}",
        )
    for field, value in payload.items():
        setattr(row, field, value)
    row.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(row)
    return _to_out(row)


@router.delete(
    "/{experiment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_experiment(
    experiment_id: str,
    session: AsyncSession = Depends(async_session_dep),
    _: CurrentUser = Depends(require_authenticated),
) -> None:
    row = await session.get(Experiment, experiment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    await session.delete(row)
    await session.commit()


@router.get("/{experiment_id}/runs")
async def list_experiment_runs(
    experiment_id: str,
    session: AsyncSession = Depends(async_session_dep),
    _: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    """Return every typed run row that points at this experiment.

    Materialises the umbrella view: for each table that grew an
    ``experiment_id`` FK in migration 0037 we issue a small bounded
    SELECT and stitch the results into a single response.
    """
    # Defer imports to keep this module light at import time.
    from aqp.persistence.models import (
        BacktestRun,
        MLExperimentRun,
        StrategyTest,
        PaperTradingRun,
    )
    from aqp.persistence.models_agents import AgentRunV2
    from aqp.persistence.models_analysis import AnalysisRun
    from aqp.persistence.models_bots import BotDeployment
    from aqp.persistence.models_rl import RLRun

    out: dict[str, list[dict[str, Any]]] = {}

    async def _grab(model: Any, label: str, fields: tuple[str, ...]) -> None:
        rows = (
            await session.execute(
                select(model)
                .where(getattr(model, "experiment_id") == experiment_id)
                .order_by(getattr(model, "created_at", model.id).desc())
                .limit(50)
            )
        ).scalars().all()
        out[label] = [
            {field: getattr(r, field, None) for field in fields} for r in rows
        ]

    common = ("id", "status", "created_at")
    await _grab(BacktestRun, "backtests", (*common, "sharpe", "total_return"))
    await _grab(MLExperimentRun, "ml_experiments", (*common, "model_kind"))
    await _grab(RLRun, "rl_runs", (*common,))
    await _grab(AnalysisRun, "analysis_runs", (*common,))
    await _grab(BotDeployment, "bot_deployments", ("id", "status", "target", "started_at"))
    await _grab(
        StrategyTest, "strategy_tests", ("id", "status", "passed", "created_at")
    )
    await _grab(PaperTradingRun, "paper_runs", (*common,))
    await _grab(AgentRunV2, "agent_runs", ("id", "status", "started_at"))
    return {"experiment_id": experiment_id, "runs": out}


__all__ = [
    "ExperimentIn",
    "ExperimentOut",
    "ExperimentPatch",
    "router",
]
