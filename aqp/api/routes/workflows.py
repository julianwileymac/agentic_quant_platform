"""REST endpoints for the additive orchestration workflow studio.

CRUD + run + replay + halt over :class:`aqp.agents.orchestration.spec.WorkflowSpec`.
Mirrors the AgentSpec route patterns in
[aqp/api/routes/agent_specs.py](agent_specs.py): every long-running
op enqueues a Celery task and returns a ``TaskAccepted`` shape; the
routes never import :mod:`celery_app` at module top (rule from
tasks-api.mdc) — the import lives inside the route bodies.

Gating
------
The router is mounted unconditionally so the existence-check by
:mod:`aqp.api.main` doesn't trip, but every route checks
``settings.orchestration_studio_enabled`` and returns ``503`` when
the flag is off. The Phase 0 rollout doc documents the flip order.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.security import secure_router
from aqp.config import settings
from aqp.persistence.db import get_session

logger = logging.getLogger(__name__)

router = secure_router(prefix="/workflows", tags=["workflows", "orchestration"], default_scope="agent:view")


# ----------------------------------------------------------------------------
# Request / response shapes
# ----------------------------------------------------------------------------


class WorkflowSpecPayload(BaseModel):
    """Subset of :class:`WorkflowSpec` fields exposed over the API."""

    name: str
    adapter: str
    description: str = ""
    adapter_kind: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    max_rounds: int = 1
    annotations: list[str] = Field(default_factory=list)
    template_target: str = "utility"


class WorkflowSpecSummary(BaseModel):
    name: str
    adapter: str
    description: str = ""
    snapshot_hash: str
    annotations: list[str] = Field(default_factory=list)
    template_target: str = "utility"


class WorkflowSpecDetail(WorkflowSpecSummary):
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunSummary(BaseModel):
    id: str
    workflow_spec_name: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    cost_usd: float = 0.0
    duration_ms: float | None = None
    halted: bool = False
    error: str | None = None


class WorkflowRunDetail(WorkflowRunSummary):
    spec_version_id: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    final_state: dict[str, Any] = Field(default_factory=dict)
    breadcrumbs: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowRunRequest(BaseModel):
    spec_name: str
    inputs: dict[str, Any] = Field(default_factory=dict)


class WorkflowHaltRequest(BaseModel):
    run_id: str | None = Field(
        default=None,
        description=(
            "Optional run id to halt. When omitted, halts every "
            "currently-running workflow."
        ),
    )
    reason: str = "user_halt"


class TaskAccepted(BaseModel):
    task_id: str
    status: str = "accepted"


# ----------------------------------------------------------------------------
# Gating helper
# ----------------------------------------------------------------------------


def _require_studio_flag() -> None:
    if not getattr(settings, "orchestration_studio_enabled", False):
        raise HTTPException(
            status_code=503,
            detail=(
                "workflow studio disabled — set "
                "AQP_ORCHESTRATION_STUDIO_ENABLED=true and reload "
                "to enable the /workflows/* surface"
            ),
        )


# ----------------------------------------------------------------------------
# Spec CRUD
# ----------------------------------------------------------------------------


@router.post("", response_model=WorkflowSpecDetail)
def create_workflow(spec: WorkflowSpecPayload) -> WorkflowSpecDetail:
    _require_studio_flag()
    from aqp.agents.orchestration.registry_specs import (
        add_workflow_spec,
        persist_spec,
    )
    from aqp.agents.orchestration.spec import WorkflowSpec

    try:
        ws = WorkflowSpec.model_validate(spec.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid spec: {exc}") from exc

    add_workflow_spec(ws)
    persist_spec(ws)  # no-op when versioning flag is off
    return _spec_detail(ws)


@router.get("", response_model=list[WorkflowSpecSummary])
def list_workflows() -> list[WorkflowSpecSummary]:
    _require_studio_flag()
    from aqp.agents.orchestration.registry_specs import list_workflow_specs

    return [_spec_summary(s) for s in list_workflow_specs()]


@router.get("/{name}", response_model=WorkflowSpecDetail)
def get_workflow(name: str) -> WorkflowSpecDetail:
    _require_studio_flag()
    from aqp.agents.orchestration.registry_specs import get_workflow_spec

    try:
        spec = get_workflow_spec(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _spec_detail(spec)


@router.get("/{name}/versions")
def list_workflow_versions(
    name: str, limit: int = Query(default=50, ge=1, le=500)
) -> list[dict[str, Any]]:
    _require_studio_flag()
    try:
        from aqp.persistence.models_workflows import (
            WorkflowSpecRow,
            WorkflowSpecVersion,
        )
    except Exception:  # noqa: BLE001
        return []

    with get_session() as session:
        row = session.execute(
            select(WorkflowSpecRow).where(WorkflowSpecRow.name == name)
        ).scalar_one_or_none()
        if row is None:
            return []
        stmt = (
            select(WorkflowSpecVersion)
            .where(WorkflowSpecVersion.spec_id == row.id)
            .order_by(desc(WorkflowSpecVersion.version))
            .limit(limit)
        )
        versions = session.execute(stmt).scalars().all()
        return [
            {
                "id": v.id,
                "version": v.version,
                "spec_hash": v.spec_hash,
                "notes": v.notes,
                "created_at": str(v.created_at) if v.created_at else None,
            }
            for v in versions
        ]


# ----------------------------------------------------------------------------
# Runs
# ----------------------------------------------------------------------------


@router.post("/{name}/run", response_model=TaskAccepted)
def run_workflow(name: str, req: WorkflowRunRequest) -> TaskAccepted:
    _require_studio_flag()
    from aqp.agents.orchestration.registry_specs import (
        get_workflow_spec,
        persist_spec,
    )
    from aqp.tasks.orchestration_tasks import (  # noqa: F401 - inline import per rule
        run_workflow as run_workflow_task,
    )

    try:
        spec = get_workflow_spec(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    spec_version_id = persist_spec(spec)
    async_result = run_workflow_task.apply_async(
        kwargs={
            "spec_name": spec.name,
            "spec_version_id": spec_version_id,
            "inputs": req.inputs or {},
        }
    )
    return TaskAccepted(task_id=str(async_result.id))


@router.post("/runs/{run_id}/replay", response_model=TaskAccepted)
def replay_run(run_id: str) -> TaskAccepted:
    _require_studio_flag()
    from aqp.tasks.orchestration_tasks import (  # noqa: F401 - inline import per rule
        replay_run as replay_run_task,
    )

    async_result = replay_run_task.apply_async(kwargs={"run_id": run_id})
    return TaskAccepted(task_id=str(async_result.id))


@router.get("/runs", response_model=list[WorkflowRunSummary])
def list_runs(
    spec_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[WorkflowRunSummary]:
    _require_studio_flag()
    try:
        from aqp.persistence.models_workflows import WorkflowRun
    except Exception:  # noqa: BLE001
        return []
    with get_session() as session:
        stmt = select(WorkflowRun)
        if spec_name:
            stmt = stmt.where(WorkflowRun.workflow_spec_name == spec_name)
        if status:
            stmt = stmt.where(WorkflowRun.status == status)
        stmt = stmt.order_by(desc(WorkflowRun.started_at)).limit(limit)
        rows = session.execute(stmt).scalars().all()
    return [_run_summary(r) for r in rows]


@router.get("/runs/{run_id}", response_model=WorkflowRunDetail)
def get_run(run_id: str) -> WorkflowRunDetail:
    _require_studio_flag()
    try:
        from aqp.persistence.models_workflows import WorkflowRun
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"workflow_runs table not provisioned: {exc}",
        ) from exc
    with get_session() as session:
        row = (
            session.query(WorkflowRun).filter(WorkflowRun.id == run_id).one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="run not found")
        return WorkflowRunDetail(
            id=str(row.id),
            workflow_spec_name=row.workflow_spec_name,
            status=row.status,
            started_at=str(row.started_at) if row.started_at else None,
            completed_at=str(row.completed_at) if row.completed_at else None,
            cost_usd=float(row.cost_usd or 0.0),
            duration_ms=float(row.duration_ms or 0.0) if row.duration_ms else None,
            halted=bool(row.halted),
            error=row.error,
            spec_version_id=row.spec_version_id,
            inputs=dict(row.inputs or {}),
            final_state=dict(row.final_state or {}),
            breadcrumbs=list(row.breadcrumbs or []),
        )


# ----------------------------------------------------------------------------
# Halt (mirrors the five existing halt endpoints)
# ----------------------------------------------------------------------------


@router.post("/halt")
def halt_workflows(req: WorkflowHaltRequest) -> dict[str, Any]:
    """Halt one (or every) running workflow.

    Mirrors :func:`/agents/halt`, :func:`/paper/stop-all`,
    :func:`/bots/halt-all`, :func:`/rl/halt-all`, and
    :func:`/quant-agents/halt`. Updates the matching ``workflow_runs``
    row(s) to ``status='halted'`` and revokes the linked Celery
    ``task_id`` so the in-flight :class:`WorkflowRuntime` exits at the
    next halt-check.
    """
    _require_studio_flag()
    halted = _halt_runs(run_id=req.run_id, reason=req.reason)
    return {"ok": True, "halted_count": len(halted), "halted": halted}


def _halt_runs(*, run_id: str | None, reason: str) -> list[dict[str, Any]]:
    """Mutate the run rows + best-effort revoke their Celery tasks.

    Degrades cleanly when ``workflow_runs`` isn't yet provisioned
    (the Phase 5 alembic migration hasn't applied) — returns an
    empty halted list rather than 500'ing the API.

    Also pushes a per-run ``aqp:workflow:halt:<run_id>`` Redis flag
    (TTL 1h) so an in-flight :class:`WorkflowRuntime` polling
    ``ctx.is_halted()`` exits at the next tick even if the Celery
    revoke signal raced with a long-running adapter inner step.
    """
    try:
        from datetime import datetime

        from aqp.persistence.models_workflows import WorkflowRun
    except Exception:  # noqa: BLE001
        return []
    halted: list[dict[str, Any]] = []
    try:
        with get_session() as session:
            q = session.query(WorkflowRun).filter(
                WorkflowRun.status.in_(("pending", "running"))
            )
            if run_id:
                q = q.filter(WorkflowRun.id == run_id)
            rows = q.all()
            for row in rows:
                task_id = row.task_id
                row.status = "halted"
                row.halted = True
                row.error = reason
                row.completed_at = datetime.utcnow()
                halted.append(
                    {
                        "run_id": str(row.id),
                        "task_id": task_id,
                        "reason": reason,
                    }
                )
            session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.debug("_halt_runs swallowed exception: %s", exc, exc_info=True)
        return halted
    # Best-effort revoke outside the DB session.
    for entry in halted:
        try:
            from aqp.tasks.celery_app import celery_app

            if entry["task_id"]:
                celery_app.control.revoke(
                    entry["task_id"], terminate=True, signal="SIGTERM"
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("workflow halt revoke failed: %s", exc)
    # Per-run Redis halt flag — keeps in-flight runtimes from racing
    # past the Celery revoke (defect 3 fix). Best-effort: failures
    # never block the API response.
    if halted:
        try:
            from aqp.config import settings as _settings

            redis_url = getattr(_settings, "redis_url", None)
            if redis_url:
                import redis  # type: ignore[import-not-found]

                client = redis.Redis.from_url(redis_url, socket_timeout=0.25)
                for entry in halted:
                    try:
                        client.set(
                            f"aqp:workflow:halt:{entry['run_id']}",
                            reason,
                            ex=3600,
                        )
                    except Exception:  # noqa: BLE001
                        continue
        except Exception:  # noqa: BLE001
            logger.debug("workflow halt redis flag set failed", exc_info=True)
    return halted


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _spec_summary(spec: Any) -> WorkflowSpecSummary:
    return WorkflowSpecSummary(
        name=spec.name,
        adapter=spec.adapter,
        description=spec.description,
        snapshot_hash=spec.snapshot_hash(),
        annotations=list(spec.annotations or []),
        template_target=getattr(spec, "template_target", "utility"),
    )


def _spec_detail(spec: Any) -> WorkflowSpecDetail:
    return WorkflowSpecDetail(
        name=spec.name,
        adapter=spec.adapter,
        description=spec.description,
        snapshot_hash=spec.snapshot_hash(),
        annotations=list(spec.annotations or []),
        template_target=getattr(spec, "template_target", "utility"),
        payload=spec.model_dump(mode="json"),
    )


def _run_summary(row: Any) -> WorkflowRunSummary:
    return WorkflowRunSummary(
        id=str(row.id),
        workflow_spec_name=row.workflow_spec_name,
        status=row.status,
        started_at=str(row.started_at) if row.started_at else None,
        completed_at=str(row.completed_at) if row.completed_at else None,
        cost_usd=float(row.cost_usd or 0.0),
        duration_ms=float(row.duration_ms or 0.0) if row.duration_ms else None,
        halted=bool(row.halted),
        error=row.error,
    )
