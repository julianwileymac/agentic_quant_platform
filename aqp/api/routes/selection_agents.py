"""REST endpoints for the selection-agent team."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.schemas import TaskAccepted
from aqp.persistence.db import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/selection", tags=["agents", "selection"])


class SelectionRequest(BaseModel):
    candidate_universe: list[str] = Field(..., min_length=1)
    model: str
    strategy: str
    target_horizon: str = "20d"
    n: int = 10
    preferences: dict[str, Any] = Field(default_factory=dict)


@router.post("/run", response_model=TaskAccepted, status_code=202)
def run_selection(req: SelectionRequest) -> TaskAccepted:
    from aqp.tasks.selection_tasks import run_stock_selector

    t = run_stock_selector.delay(**req.model_dump())
    return TaskAccepted(task_id=t.id, stream_url=f"/ws/progress/{t.id}")


@router.post("/sync")
def sync_selection(req: SelectionRequest) -> dict[str, Any]:
    from aqp.agents.registry import get_agent_spec
    from aqp.agents.runtime import AgentRuntime

    return AgentRuntime(get_agent_spec("selection.stock_selector")).run(req.model_dump()).to_dict()


@router.get("/runs")
def list_runs(
    spec_name: str = Query(default="selection.stock_selector"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    from aqp.persistence.models_agents import AgentRunV2

    with get_session() as session:
        stmt = (
            select(AgentRunV2)
            .where(AgentRunV2.spec_name == spec_name)
            .order_by(desc(AgentRunV2.started_at))
            .limit(limit)
        )
        rows = session.execute(stmt).scalars().all()
    return [
        {
            "id": r.id,
            "status": r.status,
            "task_id": r.task_id,
            "cost_usd": float(r.cost_usd or 0.0),
            "n_calls": int(r.n_calls or 0),
            "n_rag_hits": int(r.n_rag_hits or 0),
            "started_at": str(r.started_at) if r.started_at else None,
            "completed_at": str(r.completed_at) if r.completed_at else None,
        }
        for r in rows
    ]


@router.get("/annotations")
def list_annotations(
    spec_name: str = Query(default="selection.stock_selector"),
    vt_symbol: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    from aqp.persistence.models_agents import AgentAnnotation

    with get_session() as session:
        stmt = select(AgentAnnotation).where(AgentAnnotation.spec_name == spec_name)
        if vt_symbol:
            stmt = stmt.where(AgentAnnotation.vt_symbol == vt_symbol)
        stmt = stmt.order_by(desc(AgentAnnotation.created_at)).limit(limit)
        rows = session.execute(stmt).scalars().all()
    return [
        {
            "id": r.id,
            "spec_name": r.spec_name,
            "label": r.label,
            "vt_symbol": r.vt_symbol,
            "notes": r.notes,
            "payload": r.payload or {},
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r in rows
    ]
