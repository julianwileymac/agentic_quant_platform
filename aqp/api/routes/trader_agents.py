"""REST endpoints for the spec-driven trader agent."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aqp.api.schemas import TaskAccepted

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/trader", tags=["agents", "trader"])


class SignalRequest(BaseModel):
    vt_symbol: str
    as_of: str | None = None
    horizon: str = "1d"
    extras: dict[str, Any] = Field(default_factory=dict)


class BacktestWithAgentRequest(BaseModel):
    vt_symbols: list[str] = Field(..., min_length=1)
    start: str
    end: str
    spec_name: str = Field(default="trader.signal_emitter")
    extras: dict[str, Any] = Field(default_factory=dict)


@router.post("/signal", response_model=TaskAccepted, status_code=202)
def emit_signal(req: SignalRequest) -> TaskAccepted:
    from aqp.agents.registry import get_agent_spec
    from aqp.tasks.research_tasks import _run_spec  # reused thin wrapper

    try:
        get_agent_spec("trader.signal_emitter")
    except KeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # We piggy-back on the same generic helper, but go through the
    # research_tasks wrapper for consistent telemetry.
    from aqp.tasks.research_tasks import run_universe_selector  # type: ignore[unused-import]

    payload = {"vt_symbol": req.vt_symbol, "as_of": req.as_of, "horizon": req.horizon, **req.extras}
    # Synchronous emit by default — signals are short.
    out = _run_spec("trader.signal_emitter", payload)
    return TaskAccepted(task_id=out.get("run_id", "local"), status="completed")


@router.post("/sync")
def sync_signal(req: SignalRequest) -> dict[str, Any]:
    from aqp.agents.registry import get_agent_spec
    from aqp.agents.runtime import AgentRuntime

    payload = {"vt_symbol": req.vt_symbol, "as_of": req.as_of, "horizon": req.horizon, **req.extras}
    return AgentRuntime(get_agent_spec("trader.signal_emitter")).run(payload).to_dict()


@router.post("/backtest-with-agent", response_model=TaskAccepted, status_code=202)
def backtest_with_agent(req: BacktestWithAgentRequest) -> TaskAccepted:
    """Kick off an agentic backtest using the spec-driven trader.

    Reuses the existing :mod:`aqp.tasks.agentic_backtest_tasks` queue
    so the run shows up alongside legacy agentic backtests in the UI.
    """
    try:
        from aqp.tasks.agentic_backtest_tasks import run_agentic_backtest

        t = run_agentic_backtest.delay(
            symbols=req.vt_symbols,
            start=req.start,
            end=req.end,
            spec_name=req.spec_name,
            extras=req.extras,
        )
        return TaskAccepted(task_id=t.id, stream_url=f"/ws/progress/{t.id}")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"agentic backtest unavailable: {exc}") from exc
