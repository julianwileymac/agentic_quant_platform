"""Assistant Engine REST + WebSocket surface.

Mirrors the Workflow Studio routes in
:mod:`aqp.api.routes.workflows`: every long-running op enqueues a
Celery task and returns a ``TaskAccepted`` shape; routes never
import ``celery_app`` at module top — the import lives inside the
route bodies (rule from tasks-api.mdc).

Gating
------
Every mutating / DB-touching route checks
``settings.assistant_engine_enabled`` and returns 503 when off, so the
new surface stays dormant until an operator opts in. The websocket
stream stays open regardless because the underlying broker is shared
with chat / agents / workflows.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.security import secure_router
from aqp.auth.context import RequestContext
from aqp.auth.deps import current_context
from aqp.config import settings
from aqp.persistence.db import get_session
from aqp.ws.broker import asubscribe

logger = logging.getLogger(__name__)

router = secure_router(prefix="/assistants", tags=["assistants"], default_scope="agent:view")


# ----------------------------------------------------------------------------
# Request / response shapes
# ----------------------------------------------------------------------------


class AssistantSpecPayload(BaseModel):
    name: str
    description: str = ""
    mode: str = "agent"
    agent_spec_name: str | None = None
    workflow_spec_name: str | None = None
    system_instructions: str = ""
    starter_prompts: list[str] = Field(default_factory=list)
    model_policy: dict[str, Any] = Field(default_factory=dict)
    tool_policy: dict[str, Any] = Field(default_factory=dict)
    memory_policy: dict[str, Any] = Field(default_factory=dict)
    sandbox_policy: dict[str, Any] = Field(default_factory=dict)
    annotations: list[str] = Field(default_factory=list)
    template_target: str = "utility"
    extras: dict[str, Any] = Field(default_factory=dict)


class AssistantSpecSummary(BaseModel):
    name: str
    description: str = ""
    mode: str
    target_ref: str
    snapshot_hash: str
    annotations: list[str] = Field(default_factory=list)
    template_target: str = "utility"


class AssistantSpecDetail(AssistantSpecSummary):
    payload: dict[str, Any] = Field(default_factory=dict)


class AssistantSessionCreate(BaseModel):
    title: str | None = None


class AssistantSessionSummary(BaseModel):
    id: str
    assistant_spec_name: str
    title: str | None = None
    created_at: str | None = None
    last_active_at: str | None = None
    closed_at: str | None = None


class AssistantMessageRequest(BaseModel):
    prompt: str
    session_id: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)


class TaskAccepted(BaseModel):
    task_id: str
    status: str = "accepted"
    stream_url: str


class AssistantRunSummary(BaseModel):
    id: str
    assistant_spec_name: str
    status: str
    target_kind: str
    target_ref: str
    target_run_kind: str | None = None
    target_run_id: str | None = None
    task_id: str | None = None
    session_id: str | None = None
    cost_usd: float = 0.0
    halted: bool = False
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None


class AssistantRunDetail(AssistantRunSummary):
    spec_version_id: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)


class AssistantHaltRequest(BaseModel):
    run_id: str | None = Field(
        default=None,
        description=(
            "Optional run id to halt. When omitted, halts every "
            "currently-running assistant."
        ),
    )
    reason: str = "user_halt"


# ----------------------------------------------------------------------------
# Gating helper
# ----------------------------------------------------------------------------


def _require_engine_flag() -> None:
    if not getattr(settings, "assistant_engine_enabled", False):
        raise HTTPException(
            status_code=503,
            detail=(
                "assistant engine disabled — set "
                "AQP_ASSISTANT_ENGINE_ENABLED=true and reload to "
                "enable the /assistants/* surface"
            ),
        )


# ----------------------------------------------------------------------------
# Skills (read-only, always available)
# ----------------------------------------------------------------------------


@router.get("/skills")
def list_skills() -> list[dict[str, Any]]:
    """Markdown skill catalog. Read-only, no engine flag required."""
    from aqp.assistants.skills import list_markdown_skills

    return [
        {
            "slug": skill.slug,
            "title": skill.title,
            "content_hash": skill.content_hash,
            "path": skill.path,
            "tags": list(skill.tags),
        }
        for skill in list_markdown_skills()
    ]


# ----------------------------------------------------------------------------
# Spec CRUD
# ----------------------------------------------------------------------------


@router.get("", response_model=list[AssistantSpecSummary])
def list_assistants() -> list[AssistantSpecSummary]:
    _require_engine_flag()
    from aqp.assistants.registry import list_assistant_specs

    return [_summary(spec) for spec in list_assistant_specs()]


@router.post("", response_model=AssistantSpecDetail)
def create_assistant(payload: AssistantSpecPayload) -> AssistantSpecDetail:
    _require_engine_flag()
    from aqp.assistants.registry import add_assistant_spec, persist_spec
    from aqp.assistants.spec import AssistantSpec

    try:
        spec = AssistantSpec.model_validate(payload.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"invalid assistant spec: {exc}"
        ) from exc
    add_assistant_spec(spec)
    persist_spec(spec)
    return _detail(spec)


# ----------------------------------------------------------------------------
# Sessions
# ----------------------------------------------------------------------------


@router.post("/{name}/sessions", response_model=AssistantSessionSummary)
def create_session(
    name: str,
    body: AssistantSessionCreate,
    ctx: RequestContext = Depends(current_context),
) -> AssistantSessionSummary:
    _require_engine_flag()
    from aqp.assistants.registry import get_assistant_spec
    from aqp.persistence.models_assistants import AssistantSession

    try:
        spec = get_assistant_spec(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    with get_session() as session:
        row = AssistantSession(
            assistant_spec_name=spec.name,
            title=body.title or spec.description or spec.name,
            extra={"created_by": getattr(ctx, "user_id", None)},
        )
        _stamp(row, ctx)
        session.add(row)
        session.flush()
        summary = _session_summary(row)
        session.commit()
        return summary


@router.get("/sessions/recent", response_model=list[AssistantSessionSummary])
def list_sessions(
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[AssistantSessionSummary]:
    _require_engine_flag()
    try:
        from aqp.persistence.models_assistants import AssistantSession
    except Exception:  # noqa: BLE001
        return []
    try:
        with get_session() as session:
            rows = (
                session.execute(
                    select(AssistantSession)
                    .order_by(desc(AssistantSession.last_active_at))
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [_session_summary(row) for row in rows]
    except Exception as exc:  # noqa: BLE001
        logger.debug("list_sessions degrade: %s", exc, exc_info=True)
        return []


# ----------------------------------------------------------------------------
# Messages (enqueues a Celery run)
# ----------------------------------------------------------------------------


@router.post("/{name}/messages", response_model=TaskAccepted)
def send_message(
    name: str,
    body: AssistantMessageRequest,
    ctx: RequestContext = Depends(current_context),
) -> TaskAccepted:
    _require_engine_flag()
    from aqp.assistants.registry import get_assistant_spec, persist_spec
    from aqp.tasks.assistant_tasks import (  # noqa: F401 - inline import
        run_assistant as run_assistant_task,
    )

    try:
        spec = get_assistant_spec(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    spec_version_id = persist_spec(spec)

    inputs = dict(body.inputs or {})
    inputs["prompt"] = body.prompt

    async_result = run_assistant_task.apply_async(
        kwargs={
            "assistant_spec_name": spec.name,
            "spec_version_id": spec_version_id,
            "session_id": body.session_id,
            "prompt": body.prompt,
            "inputs": inputs,
            "context": ctx.to_dict() if hasattr(ctx, "to_dict") else None,
        }
    )
    task_id = str(async_result.id)
    return TaskAccepted(task_id=task_id, stream_url=f"/assistants/stream/{task_id}")


# ----------------------------------------------------------------------------
# Runs
# ----------------------------------------------------------------------------


@router.get("/runs", response_model=list[AssistantRunSummary])
def list_runs(
    assistant_spec_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[AssistantRunSummary]:
    _require_engine_flag()
    try:
        from aqp.persistence.models_assistants import AssistantRun
    except Exception:  # noqa: BLE001
        return []
    try:
        with get_session() as session:
            stmt = select(AssistantRun)
            if assistant_spec_name:
                stmt = stmt.where(
                    AssistantRun.assistant_spec_name == assistant_spec_name
                )
            if status:
                stmt = stmt.where(AssistantRun.status == status)
            stmt = stmt.order_by(desc(AssistantRun.started_at)).limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_run_summary(row) for row in rows]
    except Exception as exc:  # noqa: BLE001
        logger.debug("list_runs degrade: %s", exc, exc_info=True)
        return []


@router.get("/runs/{run_id}", response_model=AssistantRunDetail)
def get_run(run_id: str) -> AssistantRunDetail:
    _require_engine_flag()
    try:
        from aqp.persistence.models_assistants import (
            AssistantRun,
            AssistantRunEvent,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"assistant_runs table not provisioned: {exc}",
        ) from exc

    with get_session() as session:
        row = session.get(AssistantRun, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="assistant run not found")
        event_rows = (
            session.execute(
                select(AssistantRunEvent)
                .where(AssistantRunEvent.run_id == run_id)
                .order_by(AssistantRunEvent.seq)
            )
            .scalars()
            .all()
        )
        base = _run_summary(row).model_dump()
        return AssistantRunDetail(
            **base,
            spec_version_id=row.spec_version_id,
            inputs=dict(row.inputs or {}),
            output=dict(row.output or {}),
            events=[
                {
                    "seq": event.seq,
                    "kind": event.kind,
                    "name": event.name,
                    "attributes": dict(event.attributes or {}),
                    "status": event.status,
                    "cost_usd": float(event.cost_usd or 0.0)
                    if event.cost_usd is not None
                    else None,
                    "duration_ms": float(event.duration_ms or 0.0)
                    if event.duration_ms is not None
                    else None,
                    "error": event.error,
                    "created_at": str(event.created_at) if event.created_at else None,
                }
                for event in event_rows
            ],
        )


# ----------------------------------------------------------------------------
# Halt (mirrors /workflows/halt)
# ----------------------------------------------------------------------------


@router.post("/halt")
def halt_assistants(req: AssistantHaltRequest | None = None) -> dict[str, Any]:
    """Halt one (or every) running assistant.

    Mirrors the existing halt endpoints (``/agents/halt``,
    ``/paper/stop-all``, ``/bots/halt-all``, ``/rl/halt-all``,
    ``/quant-agents/halt``, ``/workflows/halt``, ``/terraform/halt``).
    Updates the matching ``assistant_runs`` rows to ``status='halted'``,
    revokes their Celery ``task_id``, and pushes a Redis halt-flag at
    ``aqp:assistant:halt:<run_id>`` so the in-flight runtime exits at
    its next halt-check tick.
    """
    _require_engine_flag()
    payload = req or AssistantHaltRequest()
    halted = _halt_runs(run_id=payload.run_id, reason=payload.reason)
    return {"ok": True, "halted_count": len(halted), "halted": halted}


def _halt_runs(*, run_id: str | None, reason: str) -> list[dict[str, Any]]:
    try:
        from aqp.persistence.models_assistants import AssistantRun
    except Exception:  # noqa: BLE001
        return []
    halted: list[dict[str, Any]] = []
    try:
        with get_session() as session:
            q = session.query(AssistantRun).filter(
                AssistantRun.status.in_(("pending", "running"))
            )
            if run_id:
                q = q.filter(AssistantRun.id == run_id)
            rows = q.all()
            for row in rows:
                task_id = row.task_id
                row.status = "halted"
                row.halted = True
                row.halted_at = datetime.utcnow()
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
    # Best-effort Celery revoke + Redis halt flag (matches the
    # /workflows/halt fan-out so an in-flight runtime exits at the
    # next halt-check tick).
    if not halted:
        return halted
    try:
        from aqp.tasks.celery_app import celery_app

        for entry in halted:
            if entry["task_id"]:
                try:
                    celery_app.control.revoke(
                        entry["task_id"], terminate=True, signal="SIGTERM"
                    )
                except Exception:  # noqa: BLE001
                    continue
    except Exception:  # noqa: BLE001
        logger.debug("assistant halt revoke failed", exc_info=True)
    try:
        redis_url = getattr(settings, "redis_url", None)
        if redis_url:
            import redis  # type: ignore[import-not-found]

            client = redis.Redis.from_url(redis_url, socket_timeout=0.25)
            for entry in halted:
                try:
                    client.set(
                        f"aqp:assistant:halt:{entry['run_id']}",
                        reason,
                        ex=3600,
                    )
                except Exception:  # noqa: BLE001
                    continue
    except Exception:  # noqa: BLE001
        logger.debug("assistant halt redis flag set failed", exc_info=True)
    return halted


# ----------------------------------------------------------------------------
# Stream
# ----------------------------------------------------------------------------


@router.websocket("/stream/{task_id}")
async def stream(ws: WebSocket, task_id: str) -> None:
    """Stream Celery progress for an assistant run.

    Phase 3a authentication: first client frame must be
    ``{"type":"auth","token":"<JWT>"}``. See :mod:`aqp.auth.ws`.
    """
    from aqp.auth.ws import ws_authenticator

    await ws.accept()
    auth_result = await ws_authenticator.authenticate(ws)
    if auth_result is None:
        return
    try:
        async for msg in asubscribe(task_id):
            await ws.send_json(msg)
            if str(msg.get("stage")) in {"done", "error"}:
                break
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001
        logger.debug("assistant stream loop ended: %s", exc, exc_info=True)


# ----------------------------------------------------------------------------
# Spec lookup (kept last so it doesn't shadow /sessions, /runs, /halt etc.)
# ----------------------------------------------------------------------------


@router.get("/{name}", response_model=AssistantSpecDetail)
def get_assistant(name: str) -> AssistantSpecDetail:
    _require_engine_flag()
    from aqp.assistants.registry import get_assistant_spec

    try:
        spec = get_assistant_spec(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _detail(spec)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _summary(spec: Any) -> AssistantSpecSummary:
    return AssistantSpecSummary(
        name=spec.name,
        description=spec.description,
        mode=spec.mode,
        target_ref=spec.target_ref,
        snapshot_hash=spec.snapshot_hash(),
        annotations=list(spec.annotations or []),
        template_target=getattr(spec, "template_target", "utility"),
    )


def _detail(spec: Any) -> AssistantSpecDetail:
    return AssistantSpecDetail(
        **_summary(spec).model_dump(),
        payload=spec.model_dump(mode="json"),
    )


def _session_summary(row: Any) -> AssistantSessionSummary:
    return AssistantSessionSummary(
        id=str(row.id),
        assistant_spec_name=row.assistant_spec_name,
        title=row.title,
        created_at=str(row.created_at) if row.created_at else None,
        last_active_at=str(row.last_active_at) if row.last_active_at else None,
        closed_at=str(row.closed_at) if row.closed_at else None,
    )


def _run_summary(row: Any) -> AssistantRunSummary:
    return AssistantRunSummary(
        id=str(row.id),
        assistant_spec_name=row.assistant_spec_name,
        status=row.status,
        target_kind=row.target_kind,
        target_ref=row.target_ref,
        target_run_kind=row.target_run_kind,
        target_run_id=row.target_run_id,
        task_id=row.task_id,
        session_id=row.session_id,
        cost_usd=float(row.cost_usd or 0.0),
        halted=bool(row.halted),
        started_at=str(row.started_at) if row.started_at else None,
        completed_at=str(row.completed_at) if row.completed_at else None,
        error=row.error,
    )


def _stamp(row: Any, ctx: RequestContext) -> None:
    for attr_ctx, attr_row in (
        ("user_id", "owner_user_id"),
        ("workspace_id", "workspace_id"),
        ("project_id", "project_id"),
    ):
        if hasattr(row, attr_row):
            value = getattr(ctx, attr_ctx, None)
            if value:
                setattr(row, attr_row, value)


__all__ = ["router"]
