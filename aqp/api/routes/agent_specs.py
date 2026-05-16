"""REST endpoints for spec-driven agents (registry + runs + evaluations).

Lives alongside the legacy [aqp/api/routes/agents.py](agents.py) which
serves the original CrewAI research crew. New endpoints are namespaced
under ``/agents/specs``, ``/agents/runs/v2``, and ``/agents/evaluations``
so the UI can pick the right surface.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.persistence.db import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents", "specs"])


class AgentSpecSummary(BaseModel):
    name: str
    role: str
    description: str = ""
    snapshot_hash: str
    n_tools: int
    n_rag_clauses: int
    memory_kind: str
    annotations: list[str] = Field(default_factory=list)
    template_target: str = "utility"


class AgentSpecDetail(AgentSpecSummary):
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentRunV2Summary(BaseModel):
    id: str
    spec_name: str
    status: str
    cost_usd: float
    n_calls: int
    n_tool_calls: int
    n_rag_hits: int
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None


class AgentRunV2Detail(AgentRunV2Summary):
    inputs: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    spec_version_id: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)


class RunRequest(BaseModel):
    spec_name: str
    inputs: dict[str, Any] = Field(default_factory=dict)


@router.get("/specs", response_model=list[AgentSpecSummary])
def list_specs() -> list[AgentSpecSummary]:
    from aqp.agents.registry import list_agent_specs

    return [
        AgentSpecSummary(
            name=s.name,
            role=s.role,
            description=s.description,
            snapshot_hash=s.snapshot_hash(),
            n_tools=len(s.tools),
            n_rag_clauses=len(s.rag),
            memory_kind=s.memory.kind,
            annotations=s.annotations,
            template_target=getattr(s, "template_target", "utility"),
        )
        for s in list_agent_specs()
    ]


@router.get("/specs/{name}", response_model=AgentSpecDetail)
def get_spec_detail(name: str) -> AgentSpecDetail:
    from aqp.agents.registry import get_agent_spec

    try:
        s = get_agent_spec(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    payload = s.model_dump(mode="json")
    return AgentSpecDetail(
        name=s.name,
        role=s.role,
        description=s.description,
        snapshot_hash=s.snapshot_hash(),
        n_tools=len(s.tools),
        n_rag_clauses=len(s.rag),
        memory_kind=s.memory.kind,
        annotations=s.annotations,
        template_target=getattr(s, "template_target", "utility"),
        payload=payload,
    )


@router.get("/specs/{name}/versions")
def list_spec_versions(name: str, limit: int = Query(default=50, ge=1, le=500)) -> list[dict[str, Any]]:
    from aqp.persistence.models_agents import AgentSpecRow, AgentSpecVersion

    with get_session() as session:
        row = session.execute(select(AgentSpecRow).where(AgentSpecRow.name == name)).scalar_one_or_none()
        if row is None:
            return []
        stmt = (
            select(AgentSpecVersion)
            .where(AgentSpecVersion.spec_id == row.id)
            .order_by(desc(AgentSpecVersion.version))
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


@router.post("/runs/v2/sync", response_model=AgentRunV2Detail)
def run_spec_sync(req: RunRequest) -> AgentRunV2Detail:
    from aqp.agents.registry import get_agent_spec
    from aqp.agents.runtime import AgentRuntime

    try:
        spec = get_agent_spec(req.spec_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    result = AgentRuntime(spec).run(req.inputs)
    return AgentRunV2Detail(
        id=result.run_id,
        spec_name=result.spec_name,
        status=result.status,
        cost_usd=result.cost_usd,
        n_calls=result.n_calls,
        n_tool_calls=result.n_tool_calls,
        n_rag_hits=result.n_rag_hits,
        started_at=None,
        completed_at=None,
        error=result.error,
        inputs=req.inputs,
        output=result.output,
        steps=[s.__dict__ for s in result.steps],
    )


@router.get("/runs/v2", response_model=list[AgentRunV2Summary])
def list_runs_v2(
    spec_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[AgentRunV2Summary]:
    from aqp.persistence.models_agents import AgentRunV2

    with get_session() as session:
        stmt = select(AgentRunV2)
        if spec_name:
            stmt = stmt.where(AgentRunV2.spec_name == spec_name)
        if status:
            stmt = stmt.where(AgentRunV2.status == status)
        stmt = stmt.order_by(desc(AgentRunV2.started_at)).limit(limit)
        rows = session.execute(stmt).scalars().all()
    return [
        AgentRunV2Summary(
            id=r.id,
            spec_name=r.spec_name,
            status=r.status,
            cost_usd=float(r.cost_usd or 0.0),
            n_calls=int(r.n_calls or 0),
            n_tool_calls=int(r.n_tool_calls or 0),
            n_rag_hits=int(r.n_rag_hits or 0),
            started_at=str(r.started_at) if r.started_at else None,
            completed_at=str(r.completed_at) if r.completed_at else None,
            error=r.error,
        )
        for r in rows
    ]


@router.get("/runs/v2/{run_id}", response_model=AgentRunV2Detail)
def get_run_v2(run_id: str) -> AgentRunV2Detail:
    from aqp.persistence.models_agents import AgentRunStep, AgentRunV2

    with get_session() as session:
        row = session.get(AgentRunV2, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="run not found")
        steps = (
            session.query(AgentRunStep)
            .filter(AgentRunStep.run_id == run_id)
            .order_by(AgentRunStep.seq)
            .all()
        )
        return AgentRunV2Detail(
            id=row.id,
            spec_name=row.spec_name,
            status=row.status,
            cost_usd=float(row.cost_usd or 0.0),
            n_calls=int(row.n_calls or 0),
            n_tool_calls=int(row.n_tool_calls or 0),
            n_rag_hits=int(row.n_rag_hits or 0),
            started_at=str(row.started_at) if row.started_at else None,
            completed_at=str(row.completed_at) if row.completed_at else None,
            error=row.error,
            inputs=row.inputs or {},
            output=row.output or {},
            spec_version_id=row.spec_version_id,
            steps=[
                {
                    "seq": s.seq,
                    "kind": s.kind,
                    "name": s.name,
                    "inputs": s.inputs or {},
                    "output": s.output or {},
                    "cost_usd": float(s.cost_usd or 0.0),
                    "duration_ms": s.duration_ms,
                    "error": s.error,
                    "created_at": str(s.created_at) if s.created_at else None,
                }
                for s in steps
            ],
        )


@router.get("/runs/v2/{run_id}/decisions")
def list_run_decisions(run_id: str, limit: int = Query(default=200, ge=1, le=2000)) -> list[dict[str, Any]]:
    """List decisions emitted by an agent run.

    Decisions are persisted as :class:`MemoryEpisode` rows whose ``meta``
    blob carries a ``run_id``. We do a best-effort lookup keyed by that
    field; if the role-keyed memory layer has no rows for this run the
    result is an empty list (idempotent, never 500s).
    """
    from aqp.persistence.models_memory import MemoryEpisode

    with get_session() as session:
        rows = (
            session.execute(
                select(MemoryEpisode)
                .where(MemoryEpisode.meta.contains({"run_id": run_id}))
                .order_by(desc(MemoryEpisode.created_at))
                .limit(limit)
            )
            .scalars()
            .all()
        )
    out: list[dict[str, Any]] = []
    for r in rows:
        meta = r.meta or {}
        out.append(
            {
                "id": r.id,
                "run_id": run_id,
                "vt_symbol": r.vt_symbol or meta.get("vt_symbol"),
                "ts": str(r.created_at) if r.created_at else None,
                "action": meta.get("action"),
                "size_pct": meta.get("size_pct"),
                "confidence": meta.get("confidence"),
                "rationale": r.lesson or meta.get("rationale"),
                "provider": meta.get("provider"),
            }
        )
    return out


@router.get("/runs/v2/{run_id}/reflections")
def list_run_reflections(run_id: str, limit: int = Query(default=200, ge=1, le=2000)) -> list[dict[str, Any]]:
    """List reflections written by an agent run.

    Backed by :class:`MemoryReflection`; identical lookup pattern to
    :func:`list_run_decisions`. Returns ``[]`` when no reflections were
    persisted for this run.
    """
    from aqp.persistence.models_memory import MemoryReflection

    with get_session() as session:
        rows = (
            session.execute(
                select(MemoryReflection)
                .where(MemoryReflection.meta.contains({"run_id": run_id}))
                .order_by(desc(MemoryReflection.created_at))
                .limit(limit)
            )
            .scalars()
            .all()
        )
    return [
        {
            "id": r.id,
            "run_id": run_id,
            "ts": str(r.created_at) if r.created_at else None,
            "text": r.lesson,
            "tags": (r.meta or {}).get("tags") or [],
        }
        for r in rows
    ]


@router.post("/runs/v2/{run_id}/replay", response_model=AgentRunV2Detail)
def replay_run(run_id: str) -> AgentRunV2Detail:
    """Re-run an agent against the exact spec version that produced ``run_id``."""
    from aqp.agents.registry import replay_spec_version
    from aqp.agents.runtime import AgentRuntime
    from aqp.persistence.models_agents import AgentRunV2

    with get_session() as session:
        row = session.get(AgentRunV2, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="run not found")
        if not row.spec_version_id:
            raise HTTPException(status_code=400, detail="run has no spec_version_id")
        spec = replay_spec_version(row.spec_version_id)
        result = AgentRuntime(spec).run(row.inputs or {})
    return AgentRunV2Detail(
        id=result.run_id,
        spec_name=result.spec_name,
        status=result.status,
        cost_usd=result.cost_usd,
        n_calls=result.n_calls,
        n_tool_calls=result.n_tool_calls,
        n_rag_hits=result.n_rag_hits,
        started_at=None,
        completed_at=None,
        error=result.error,
        inputs=row.inputs or {},
        output=result.output,
        spec_version_id=row.spec_version_id,
        steps=[s.__dict__ for s in result.steps],
    )


@router.post("/halt")
def halt_agents(engage_risk: bool = Query(default=True)) -> dict[str, Any]:
    """Halt every running spec-driven agent run.

    Idempotent kill-switch fan-out target wired to the topbar
    ``KillSwitch`` component
    (``frontend/src/components/common/KillSwitch.tsx``). Selects every
    ``AgentRunV2`` in ``status="running"`` (or ``"pending"``) with a
    ``task_id`` and asks Celery to revoke + terminate them. Each row is
    flipped to ``status="halted"`` so the run-detail UI reflects the
    new state immediately.

    When ``engage_risk=true`` (the default) the global risk kill switch
    is also engaged so any in-flight order submissions are blocked at
    the order path while the halt rolls.
    """
    from aqp.persistence.models_agents import AgentRunV2
    from aqp.tasks.celery_app import celery_app as _celery

    revoked: list[str] = []
    failed: list[dict[str, str]] = []

    if engage_risk:
        try:
            from aqp.risk.kill_switch import engage as _engage_kill

            _engage_kill("agents.halt: kill_switch fanout")
        except Exception as exc:  # noqa: BLE001
            failed.append({"step": "engage_kill_switch", "error": str(exc)})

    with get_session() as session:
        rows = session.execute(
            select(AgentRunV2).where(AgentRunV2.status.in_(["running", "pending"]))
        ).scalars().all()
        for row in rows:
            tid = (row.task_id or "").strip()
            if tid:
                try:
                    _celery.control.revoke(tid, terminate=True, signal="SIGTERM")
                    revoked.append(tid)
                except Exception as exc:  # noqa: BLE001
                    failed.append({"task_id": tid, "error": str(exc)})
            row.status = "halted"
            row.error = (row.error or "") + "\nhalted by kill switch"

    return {
        "stopped": len(revoked),
        "task_ids": revoked,
        "failures": failed,
        "risk_kill_switch_engaged": engage_risk,
    }


@router.get("/evaluations")
def list_evaluations(
    spec_name: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    from aqp.persistence.models_agents import AgentEvaluation

    with get_session() as session:
        stmt = select(AgentEvaluation)
        if spec_name:
            stmt = stmt.where(AgentEvaluation.spec_name == spec_name)
        stmt = stmt.order_by(desc(AgentEvaluation.started_at)).limit(limit)
        rows = session.execute(stmt).scalars().all()
    return [
        {
            "id": r.id,
            "spec_name": r.spec_name,
            "eval_set_name": r.eval_set_name,
            "n_cases": r.n_cases,
            "n_passed": r.n_passed,
            "aggregate": r.aggregate or {},
            "started_at": str(r.started_at) if r.started_at else None,
            "completed_at": str(r.completed_at) if r.completed_at else None,
        }
        for r in rows
    ]
