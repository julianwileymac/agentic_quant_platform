"""REST surface for the agentic trader stack.

Endpoints
---------

- ``POST /agentic/precompute`` — schedule a Celery task that populates
  the ``DecisionCache`` for a ``(strategy, symbols, dates)`` grid.
- ``POST /agentic/backtest`` — end-to-end Quickstart: precompute then
  run the backtest with ``AgenticAlpha``; returns a ``task_id`` the
  wizard can poll on ``/chat/stream/{task_id}``.
- ``GET /agentic/decisions/{backtest_id}`` — list the decisions for a
  backtest (from the ``agent_decisions`` table).
- ``GET /agentic/debates/{crew_run_id}`` — list the debate turns for a
  crew run (from the ``debate_turns`` table).
- ``GET /agentic/cache/{strategy_id}`` — stats about the on-disk cache.
- ``GET /agentic/providers`` — list LLM providers the router knows.
- ``GET /agentic/presets`` — list YAML presets under ``configs/agents/``.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from sqlalchemy import desc, select

from pydantic import BaseModel, Field

from aqp.api.schemas import (
    AgenticBacktestRequest,
    AgenticPrecomputeRequest,
    AgentDecisionResponse,
    DebateTurnResponse,
    TaskAccepted,
)
from aqp.config import settings
from aqp.llm.providers import list_providers
from aqp.persistence.db import get_session
from aqp.persistence.models import (
    AgentBacktest,
    AgentDecision,
    AgentJudgeReport,
    AgentReplayRun,
    DebateTurn,
)
from aqp.tasks.agentic_backtest_tasks import (
    precompute_decisions,
    run_agentic_backtest,
    run_agentic_judge,
    run_agentic_replay,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agentic", tags=["agentic"])


_CONFIGS_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "configs"


def _default_strategy_config() -> dict[str, Any]:
    """Load the Quickstart YAML strategy template."""
    path = _CONFIGS_ROOT / "strategies" / "agentic_trader_quickstart.yaml"
    if not path.exists():
        raise HTTPException(500, f"Quickstart template not found at {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@router.post("/precompute", response_model=TaskAccepted)
def precompute(req: AgenticPrecomputeRequest) -> TaskAccepted:
    async_result = precompute_decisions.delay(
        strategy_id=req.strategy_id,
        symbols=req.symbols,
        start=req.start,
        end=req.end,
        preset=req.preset,
        overrides=req.overrides or {},
        rebalance_frequency=req.rebalance_frequency,
    )
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.post("/backtest", response_model=TaskAccepted)
def backtest(req: AgenticBacktestRequest) -> TaskAccepted:
    cfg = req.config or _default_strategy_config()
    async_result = run_agentic_backtest.delay(
        cfg=cfg,
        symbols=req.symbols,
        start=req.start,
        end=req.end,
        strategy_id=req.strategy_id,
        run_name=req.run_name,
        preset=req.preset,
        provider=req.provider or None,
        deep_model=req.deep_model or None,
        quick_model=req.quick_model or None,
        max_debate_rounds=req.max_debate_rounds,
        rebalance_frequency=req.rebalance_frequency,
        mode=req.mode,
        skip_precompute=req.skip_precompute,
    )
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.get("/decisions/{backtest_id}", response_model=list[AgentDecisionResponse])
def list_decisions(backtest_id: str, limit: int = 500) -> list[AgentDecisionResponse]:
    with get_session() as s:
        rows = s.execute(
            select(AgentDecision)
            .where(AgentDecision.backtest_id == backtest_id)
            .order_by(AgentDecision.ts.asc())
            .limit(limit)
        ).scalars().all()
    return [
        AgentDecisionResponse(
            id=r.id,
            vt_symbol=r.vt_symbol,
            ts=r.ts,
            action=r.action,
            size_pct=float(r.size_pct or 0.0),
            confidence=float(r.confidence or 0.5),
            rating=r.rating,
            rationale=r.rationale,
            token_cost_usd=float(r.token_cost_usd or 0.0),
            provider=r.provider,
            deep_model=r.deep_model,
            quick_model=r.quick_model,
            crew_run_id=r.crew_run_id,
        )
        for r in rows
    ]


@router.get("/debates/{crew_run_id}", response_model=list[DebateTurnResponse])
def list_debates(crew_run_id: str) -> list[DebateTurnResponse]:
    with get_session() as s:
        rows = s.execute(
            select(DebateTurn)
            .where(DebateTurn.crew_run_id == crew_run_id)
            .order_by(DebateTurn.round.asc(), desc(DebateTurn.side))
        ).scalars().all()
    return [
        DebateTurnResponse(
            id=r.id,
            round=int(r.round or 0),
            side=r.side,
            argument=r.argument,
            cites=list(r.cites or []),
            token_cost_usd=float(r.token_cost_usd or 0.0),
        )
        for r in rows
    ]


@router.get("/sidecar/{backtest_id}")
def get_sidecar(backtest_id: str) -> dict[str, Any]:
    """Return the :class:`AgentBacktest` sidecar row, or 404."""
    with get_session() as s:
        row = s.execute(
            select(AgentBacktest).where(AgentBacktest.backtest_id == backtest_id)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, f"no agentic sidecar for backtest {backtest_id}")
        return {
            "id": row.id,
            "backtest_id": row.backtest_id,
            "mode": row.mode,
            "provider": row.provider,
            "deep_model": row.deep_model,
            "quick_model": row.quick_model,
            "max_debate_rounds": row.max_debate_rounds,
            "n_decisions": row.n_decisions,
            "n_debate_turns": row.n_debate_turns,
            "total_token_cost_usd": row.total_token_cost_usd,
            "decision_cache_uri": row.decision_cache_uri,
        }


@router.get("/cache/{strategy_id}")
def cache_stats(strategy_id: str) -> dict[str, Any]:
    from aqp.agents.trading.decision_cache import DecisionCache

    cache = DecisionCache(strategy_id=strategy_id)
    df = cache.scan()
    return {
        "strategy_id": strategy_id,
        "cache_uri": str(cache.root),
        "n_decisions": int(len(df)),
        "total_cost_usd": float(df["token_cost_usd"].sum()) if not df.empty else 0.0,
        "symbols": sorted(set(df["vt_symbol"])) if not df.empty else [],
        "first_ts": str(df["timestamp"].min()) if not df.empty else None,
        "last_ts": str(df["timestamp"].max()) if not df.empty else None,
    }


@router.get("/providers")
def providers() -> dict[str, Any]:
    """Expose the provider catalog so the UI wizard can populate dropdowns."""
    from aqp.llm.providers.catalog import PROVIDERS

    return {
        "active": settings.llm_provider,
        "providers": [
            {
                "slug": p.slug,
                "default_deep_model": p.default_deep_model,
                "default_quick_model": p.default_quick_model,
                "requires_api_key": p.requires_api_key,
                "key_configured": bool(settings.api_key_for_provider(p.slug))
                if p.requires_api_key
                else True,
            }
            for p in PROVIDERS.values()
        ],
        "available": list_providers(),
    }


# ---------------------------------------------------------------------------
# HITL phase 1: LLM/agent-as-judge + post-hoc replay endpoints.
# ---------------------------------------------------------------------------


class JudgeRequest(BaseModel):
    judge: dict[str, Any] = Field(
        default_factory=lambda: {
            "class": "LLMJudge",
            "module_path": "aqp.backtest.llm_judge",
            "kwargs": {"tier": "deep", "rubric": "default"},
        },
        description="``{class, module_path, kwargs}`` build-spec for the judge.",
    )


class JudgeReportResponse(BaseModel):
    id: str
    backtest_id: str
    judge_class: str
    score: float
    summary: str | None = None
    findings: list[dict[str, Any]] = Field(default_factory=list)
    cost_usd: float = 0.0
    provider: str | None = None
    model: str | None = None
    rubric: str | None = None
    created_at: Any = None


class FindingEdit(BaseModel):
    decision_id: str
    action: str | None = None
    size_pct: float | None = None
    rationale: str | None = None


class ReplayRequest(BaseModel):
    edits: list[FindingEdit] = Field(default_factory=list)
    note: str | None = None
    created_by: str | None = None
    judge_report_id: str | None = None


class ReplayRunResponse(BaseModel):
    id: str
    parent_backtest_id: str
    child_backtest_id: str | None = None
    judge_report_id: str | None = None
    status: str
    n_edits: int = 0
    note: str | None = None
    created_by: str | None = None
    error: str | None = None
    created_at: Any = None
    completed_at: Any = None


@router.get("/judges")
def list_judges() -> dict[str, Any]:
    """Enumerate registered ``kind=judge`` classes for the wizard dropdown."""
    from aqp.core.registry import get_tags, list_by_kind

    # Force-import the judge module so the registry is populated.
    try:
        import aqp.backtest.llm_judge  # noqa: F401
    except Exception:
        logger.exception("could not import aqp.backtest.llm_judge")

    bucket = list_by_kind("judge")
    return {
        "judges": [
            {
                "alias": alias,
                "qualname": f"{cls.__module__}.{cls.__name__}",
                "tags": sorted(t for t in get_tags(cls) if not t.startswith("kind:")),
            }
            for alias, cls in sorted(bucket.items())
        ]
    }


@router.post("/judge/{backtest_id}", response_model=TaskAccepted)
def submit_judge(backtest_id: str, req: JudgeRequest | None = None) -> TaskAccepted:
    judge_cfg = (req.judge if req else None) or {
        "class": "LLMJudge",
        "module_path": "aqp.backtest.llm_judge",
        "kwargs": {"tier": "deep", "rubric": "default"},
    }
    async_result = run_agentic_judge.delay(backtest_id, judge_cfg)
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.get("/judge/{backtest_id}", response_model=list[JudgeReportResponse])
def list_judge_reports(backtest_id: str) -> list[JudgeReportResponse]:
    with get_session() as s:
        rows = (
            s.execute(
                select(AgentJudgeReport)
                .where(AgentJudgeReport.backtest_id == backtest_id)
                .order_by(desc(AgentJudgeReport.created_at))
            )
            .scalars()
            .all()
        )
    return [
        JudgeReportResponse(
            id=r.id,
            backtest_id=r.backtest_id,
            judge_class=r.judge_class,
            score=float(r.score or 0.0),
            summary=r.summary,
            findings=list(r.findings or []),
            cost_usd=float(r.cost_usd or 0.0),
            provider=r.provider,
            model=r.model,
            rubric=r.rubric,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/replay/{backtest_id}", response_model=TaskAccepted)
def submit_replay(backtest_id: str, req: ReplayRequest) -> TaskAccepted:
    edits = [e.model_dump(exclude_none=True) for e in req.edits]
    async_result = run_agentic_replay.delay(
        backtest_id,
        edits,
        note=req.note,
        created_by=req.created_by,
        judge_report_id=req.judge_report_id,
    )
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.get("/replay", response_model=list[ReplayRunResponse])
def list_replays(
    parent_backtest_id: str | None = None,
    limit: int = 50,
) -> list[ReplayRunResponse]:
    with get_session() as s:
        stmt = select(AgentReplayRun).order_by(desc(AgentReplayRun.created_at)).limit(limit)
        if parent_backtest_id:
            stmt = stmt.where(AgentReplayRun.parent_backtest_id == parent_backtest_id)
        rows = s.execute(stmt).scalars().all()
    return [
        ReplayRunResponse(
            id=r.id,
            parent_backtest_id=r.parent_backtest_id,
            child_backtest_id=r.child_backtest_id,
            judge_report_id=r.judge_report_id,
            status=r.status,
            n_edits=len(r.edits or []),
            note=r.note,
            created_by=r.created_by,
            error=r.error,
            created_at=r.created_at,
            completed_at=r.completed_at,
        )
        for r in rows
    ]


@router.get("/replay/{replay_id}", response_model=ReplayRunResponse)
def get_replay(replay_id: str) -> ReplayRunResponse:
    with get_session() as s:
        r = s.get(AgentReplayRun, replay_id)
        if r is None:
            raise HTTPException(404, f"no replay run {replay_id}")
        return ReplayRunResponse(
            id=r.id,
            parent_backtest_id=r.parent_backtest_id,
            child_backtest_id=r.child_backtest_id,
            judge_report_id=r.judge_report_id,
            status=r.status,
            n_edits=len(r.edits or []),
            note=r.note,
            created_by=r.created_by,
            error=r.error,
            created_at=r.created_at,
            completed_at=r.completed_at,
        )


@router.get("/presets")
def presets() -> dict[str, Any]:
    """Enumerate the YAML trader-crew presets the wizard may use."""
    folder = _CONFIGS_ROOT / "agents"
    items: list[dict[str, Any]] = []
    if folder.exists():
        for path in sorted(folder.glob("trader_crew*.yaml")):
            try:
                with path.open("r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
            except Exception:
                data = {}
            items.append({
                "name": path.stem,
                "path": str(path),
                "description": data.get("description", ""),
                "max_debate_rounds": data.get("max_debate_rounds", 1),
            })
    return {"presets": items}
