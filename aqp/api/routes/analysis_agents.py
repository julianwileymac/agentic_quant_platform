"""REST endpoints for the analysis-agent team."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from aqp.api.schemas import TaskAccepted

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/analysis", tags=["agents", "analysis"])


class AnalyzeRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


@router.post("/step", response_model=TaskAccepted, status_code=202)
def analyze_step(req: AnalyzeRequest) -> TaskAccepted:
    from aqp.tasks.analysis_tasks import analyze_step as task

    t = task.delay(**req.inputs)
    return TaskAccepted(task_id=t.id, stream_url=f"/ws/progress/{t.id}")


@router.post("/run", response_model=TaskAccepted, status_code=202)
def analyze_run(req: AnalyzeRequest) -> TaskAccepted:
    from aqp.tasks.analysis_tasks import analyze_run as task

    t = task.delay(**req.inputs)
    return TaskAccepted(task_id=t.id, stream_url=f"/ws/progress/{t.id}")


@router.post("/portfolio", response_model=TaskAccepted, status_code=202)
def analyze_portfolio(req: AnalyzeRequest) -> TaskAccepted:
    from aqp.tasks.analysis_tasks import analyze_portfolio as task

    t = task.delay(**req.inputs)
    return TaskAccepted(task_id=t.id, stream_url=f"/ws/progress/{t.id}")


@router.post("/reflect", response_model=TaskAccepted, status_code=202)
def reflect(body: dict[str, Any] = Body(default_factory=dict)) -> TaskAccepted:
    """Trigger TradingAgents-style deferred outcome reflection."""
    from aqp.tasks.analysis_tasks import reflect as task

    t = task.delay(**body)
    return TaskAccepted(task_id=t.id, stream_url=f"/ws/progress/{t.id}")


@router.post("/sync/run")
def sync_run_analyst(req: AnalyzeRequest) -> dict[str, Any]:
    from aqp.agents.registry import get_agent_spec
    from aqp.agents.runtime import AgentRuntime

    return AgentRuntime(get_agent_spec("analysis.run")).run(req.inputs).to_dict()
