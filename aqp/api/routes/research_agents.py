"""REST endpoints for the research-team agents."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aqp.api.schemas import TaskAccepted

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/research", tags=["agents", "research"])


class ResearchInputs(BaseModel):
    vt_symbol: str | None = None
    universe: list[str] = Field(default_factory=list)
    as_of: str | None = None
    prompt: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


def _payload(req: ResearchInputs) -> dict[str, Any]:
    out = req.model_dump(exclude_none=True)
    extras = out.pop("extras", {})
    out.update(extras)
    return out


@router.post("/news-miner", response_model=TaskAccepted, status_code=202)
def run_news_miner(req: ResearchInputs) -> TaskAccepted:
    from aqp.tasks.research_tasks import run_news_miner as task

    t = task.delay(**_payload(req))
    return TaskAccepted(task_id=t.id, stream_url=f"/ws/progress/{t.id}")


@router.post("/equity", response_model=TaskAccepted, status_code=202)
def run_equity(req: ResearchInputs) -> TaskAccepted:
    if not req.vt_symbol and not req.prompt:
        raise HTTPException(status_code=400, detail="Provide vt_symbol or prompt")
    from aqp.tasks.research_tasks import run_equity_researcher as task

    t = task.delay(**_payload(req))
    return TaskAccepted(task_id=t.id, stream_url=f"/ws/progress/{t.id}")


@router.post("/universe", response_model=TaskAccepted, status_code=202)
def run_universe(req: ResearchInputs) -> TaskAccepted:
    from aqp.tasks.research_tasks import run_universe_selector as task

    t = task.delay(**_payload(req))
    return TaskAccepted(task_id=t.id, stream_url=f"/ws/progress/{t.id}")


@router.post("/sync/news-miner")
def sync_news_miner(req: ResearchInputs) -> dict[str, Any]:
    """Synchronous variant — runs in-process, returns the result directly."""
    from aqp.agents.registry import get_agent_spec
    from aqp.agents.runtime import AgentRuntime

    return AgentRuntime(get_agent_spec("research.news_miner")).run(_payload(req)).to_dict()
