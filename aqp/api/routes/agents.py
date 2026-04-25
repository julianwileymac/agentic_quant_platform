"""Agent crew endpoints — kickoff + registry + event log.

Besides the historical ``POST /agents/crew/run`` that dispatches a Celery
task, we now expose:

- ``GET /agents/crews`` — list every recorded crew run (task_id, prompt,
  status, agent_run_id, error).
- ``GET /agents/crews/{task_id}`` — detail + cached events.
- ``GET /agents/crews/{task_id}/events`` — ordered stream frames for the
  task (uses the Redis pub/sub backlog when available; otherwise falls
  back to the cached ``CrewRun.events`` JSON blob).

Together these give the Crew Trace UI a first-class registry instead of
needing to scrape ``/chat/stream/{task_id}`` to know what to subscribe to.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.schemas import CrewRunRequest, TaskAccepted
from aqp.persistence.db import get_session
from aqp.persistence.models import AgentRun, CrewRun
from aqp.tasks.agent_tasks import run_research_crew

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["agents"])


class CrewRunSummary(BaseModel):
    id: str
    task_id: str
    crew_name: str
    crew_type: str = "research"
    status: str
    session_id: str | None = None
    agent_run_id: str | None = None
    prompt: str
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    cost_usd: float = 0.0


class CrewRunDetail(CrewRunSummary):
    result: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/crew/run", response_model=TaskAccepted)
def kickoff_crew(req: CrewRunRequest) -> TaskAccepted:
    async_result = run_research_crew.delay(
        prompt=req.prompt,
        session_id=req.session_id,
        config_path=req.config_path,
    )
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.get("/crews", response_model=list[CrewRunSummary])
def list_crews(limit: int = 50, status: str | None = None) -> list[CrewRunSummary]:
    with get_session() as s:
        stmt = select(CrewRun).order_by(desc(CrewRun.started_at)).limit(limit)
        if status:
            stmt = stmt.where(CrewRun.status == status)
        rows = s.execute(stmt).scalars().all()
        return [_crew_summary(r) for r in rows]


@router.get("/crews/{task_id}", response_model=CrewRunDetail)
def get_crew(task_id: str) -> CrewRunDetail:
    with get_session() as s:
        row = s.execute(
            select(CrewRun).where(CrewRun.task_id == task_id)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, f"no crew run for task {task_id}")
        summary = _crew_summary(row).model_dump()
        return CrewRunDetail(
            **summary,
            result=row.result or {},
            events=list(row.events or []),
        )


@router.get("/tools")
def list_agent_tools() -> dict[str, Any]:
    """Return every tool name from the tools registry.

    Introspected purely from :data:`aqp.agents.tools.TOOL_REGISTRY` — no
    tool is instantiated, so this endpoint stays cheap and never
    triggers side-effectful imports (CrewAI's RAG module eagerly wants
    a writable HOME on first class instantiation).
    """
    import inspect

    from aqp.agents.tools import TOOL_REGISTRY

    out: list[dict[str, Any]] = []
    for name, cls in sorted(TOOL_REGISTRY.items()):
        doc = (inspect.getdoc(cls) or "").split("\n\n", 1)[0]
        args_schema: dict[str, Any] = {}
        try:
            schema = getattr(cls, "args_schema", None)
            if schema is not None and hasattr(schema, "model_json_schema"):
                args_schema = schema.model_json_schema()
            elif schema is not None and hasattr(schema, "schema"):
                args_schema = schema.schema()
        except Exception:
            args_schema = {}
        out.append(
            {
                "name": name,
                "qualname": f"{cls.__module__}.{cls.__name__}",
                "doc": doc or None,
                "args_schema": args_schema,
            }
        )
    return {"tools": out}


@router.get("/crews/{task_id}/events")
def crew_events(task_id: str, limit: int = 200) -> dict[str, Any]:
    """Return the most recent events for a task.

    For active tasks we prefer the Redis pub/sub backlog (tapped via the
    sync helper in :mod:`aqp.ws.broker`). For completed tasks we fall back
    to the ``CrewRun.events`` snapshot persisted by the worker at the end
    of a run. If neither is available we return an empty list instead of
    404-ing.
    """
    events: list[dict[str, Any]] = []
    with get_session() as s:
        row = s.execute(
            select(CrewRun).where(CrewRun.task_id == task_id)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, f"no crew run for task {task_id}")
        if row.events:
            events = list(row.events)[-limit:]

    agent_run: AgentRun | None = None
    with get_session() as s:
        agent_run = s.execute(
            select(AgentRun).where(AgentRun.task_id == task_id)
        ).scalar_one_or_none()

    return {
        "task_id": task_id,
        "events": events,
        "agent_run_id": agent_run.id if agent_run else None,
        "agent_status": agent_run.status if agent_run else None,
    }


def _crew_summary(row: CrewRun) -> CrewRunSummary:
    return CrewRunSummary(
        id=row.id,
        task_id=row.task_id,
        crew_name=row.crew_name,
        crew_type=getattr(row, "crew_type", "research") or "research",
        status=row.status,
        session_id=row.session_id,
        agent_run_id=row.agent_run_id,
        prompt=row.prompt,
        started_at=row.started_at,
        completed_at=row.completed_at,
        error=row.error,
        cost_usd=float(getattr(row, "cost_usd", 0.0) or 0.0),
    )


# ---------------------------------------------------------------------------
# FinRobot-style equity research
# ---------------------------------------------------------------------------


class EquityReportRequest(BaseModel):
    vt_symbol: str
    as_of: str
    peers: list[str] = Field(default_factory=list)
    sections: list[str] | None = None
    valuation_inputs: dict[str, Any] | None = None


class EquityReportSummary(BaseModel):
    id: str
    vt_symbol: str
    as_of: datetime
    peers: list[str] = Field(default_factory=list)
    cost_usd: float = 0.0
    status: str
    error: str | None = None
    created_at: datetime


class EquityReportDetail(EquityReportSummary):
    sections: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    valuation: dict[str, Any] = Field(default_factory=dict)
    catalysts: list[dict[str, Any]] = Field(default_factory=list)
    sensitivity: dict[str, Any] = Field(default_factory=dict)


@router.post("/equity-report", response_model=TaskAccepted)
def submit_equity_report(req: EquityReportRequest) -> TaskAccepted:
    from aqp.tasks.equity_report_tasks import run_equity_report

    async_result = run_equity_report.delay(
        vt_symbol=req.vt_symbol,
        as_of=req.as_of,
        peers=req.peers,
        sections=req.sections,
        valuation_inputs=req.valuation_inputs,
    )
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.get("/equity-report/sections")
def list_equity_sections() -> dict[str, Any]:
    """Enumerate every registered ``equity_section`` agent."""
    from aqp.core.registry import list_by_kind

    bucket = list_by_kind("equity_section")
    return {
        "sections": [
            {
                "alias": alias,
                "section_key": getattr(cls, "section_key", alias),
                "title": getattr(cls, "title", alias),
                "qualname": f"{cls.__module__}.{cls.__name__}",
            }
            for alias, cls in sorted(bucket.items())
        ]
    }


@router.get("/equity-reports", response_model=list[EquityReportSummary])
def list_equity_reports(
    vt_symbol: str | None = None,
    limit: int = 50,
) -> list[EquityReportSummary]:
    from aqp.persistence.models import EquityReport

    with get_session() as s:
        stmt = select(EquityReport).order_by(desc(EquityReport.created_at)).limit(limit)
        if vt_symbol:
            stmt = stmt.where(EquityReport.vt_symbol == vt_symbol)
        rows = s.execute(stmt).scalars().all()
    return [
        EquityReportSummary(
            id=r.id,
            vt_symbol=r.vt_symbol,
            as_of=r.as_of,
            peers=list(r.peers or []),
            cost_usd=float(r.cost_usd or 0.0),
            status=r.status,
            error=r.error,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/equity-report/{report_id}", response_model=EquityReportDetail)
def get_equity_report(report_id: str) -> EquityReportDetail:
    from aqp.persistence.models import EquityReport

    with get_session() as s:
        r = s.get(EquityReport, report_id)
        if r is None:
            raise HTTPException(404, f"no equity report {report_id}")
        return EquityReportDetail(
            id=r.id,
            vt_symbol=r.vt_symbol,
            as_of=r.as_of,
            peers=list(r.peers or []),
            sections=dict(r.sections or {}),
            usage=dict(r.usage or {}),
            valuation=dict(r.valuation or {}),
            catalysts=list(r.catalysts or []),
            sensitivity=dict(r.sensitivity or {}),
            cost_usd=float(r.cost_usd or 0.0),
            status=r.status,
            error=r.error,
            created_at=r.created_at,
        )
