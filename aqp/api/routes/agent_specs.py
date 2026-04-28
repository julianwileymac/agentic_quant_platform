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
