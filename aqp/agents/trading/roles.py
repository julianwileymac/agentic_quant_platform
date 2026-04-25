"""Role-by-role execution primitives for the trader crew.

Unlike the research crew (:mod:`aqp.agents.roles`) this module does
**not** spawn CrewAI ``Agent`` instances for every step. The trader
workflow is short, requires strict JSON outputs, and runs thousands of
times during a precompute. We therefore call the LLM router directly
and parse the response into our Pydantic types. This keeps:

- cost accounting exact (every call's ``cost_usd`` is available);
- the flow deterministic and trivially mockable in tests;
- the prompts small (no CrewAI task-scheduling overhead).

For teams who want the CrewAI agent abstraction, the same prompts can
be plugged into ``Agent`` factories — see
:func:`make_trading_crewai_agents` for a parity factory used by the UI
for live "watch the crew think" runs.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from aqp.agents.trading import prompts
from aqp.agents.trading.types import (
    AnalystReport,
    DebateTurn,
    PortfolioDecision,
    RiskVerdict,
    TraderPlan,
    parse_rating,
)
from aqp.llm.ollama_client import complete

logger = logging.getLogger(__name__)


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any]:
    """Best-effort JSON extractor that tolerates code fences and stray prose."""
    if not text:
        return {}
    s = text.strip()
    # ```json ... ``` fences are the common LLM habit.
    m = _JSON_FENCE_RE.search(s)
    if m:
        s = m.group(1).strip()
    # Fall back to first ``{ ... }`` substring.
    if not s.startswith("{"):
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            s = s[start : end + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # Try tolerant parsing of single quotes.
        try:
            return json.loads(s.replace("'", '"'))
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM JSON: %s", text[:120])
            return {}


@dataclass
class RoleResult:
    """Single LLM call result enriched with USD cost + raw text."""

    content: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    payload: dict[str, Any]


def _call_role(
    system: str,
    user: str,
    *,
    tier: str = "quick",
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> RoleResult:
    """Run one LLM call and return a :class:`RoleResult`."""
    result = complete(
        tier=tier,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        provider=provider,
        model=model,
        temperature=temperature,
    )
    payload = _extract_json(result.content)
    return RoleResult(
        content=result.content,
        model=result.model,
        provider=result.provider,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        cost_usd=result.cost_usd,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# Analyst roles
# ---------------------------------------------------------------------------


def run_fundamentals_analyst(
    vt_symbol: str,
    as_of: str,
    fundamentals: dict[str, Any],
    *,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[AnalystReport, RoleResult]:
    user = (
        f"symbol: {vt_symbol}\n"
        f"as_of: {as_of}\n"
        f"fundamentals: {json.dumps(fundamentals, default=str)}\n"
    )
    result = _call_role(
        prompts.FUNDAMENTALS_ANALYST_SYSTEM,
        user,
        tier="quick",
        provider=provider,
        model=model,
    )
    report = AnalystReport(
        role="fundamentals_analyst",
        summary=result.payload.get("summary", ""),
        evidence=list(result.payload.get("evidence", []) or []),
        confidence=float(result.payload.get("confidence", 0.5) or 0.5),
        rating=parse_rating(result.payload.get("rating")),
    )
    return report, result


def run_sentiment_analyst(
    vt_symbol: str,
    as_of: str,
    news_items: list[dict[str, Any]],
    *,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[AnalystReport, RoleResult]:
    user = (
        f"symbol: {vt_symbol}\n"
        f"as_of: {as_of}\n"
        f"headlines_with_scores: {json.dumps(news_items[:20], default=str)}\n"
    )
    result = _call_role(
        prompts.SENTIMENT_ANALYST_SYSTEM,
        user,
        tier="quick",
        provider=provider,
        model=model,
    )
    report = AnalystReport(
        role="sentiment_analyst",
        summary=result.payload.get("summary", ""),
        evidence=list(result.payload.get("evidence", []) or []),
        confidence=float(result.payload.get("confidence", 0.5) or 0.5),
        rating=parse_rating(result.payload.get("rating")),
    )
    return report, result


def run_news_analyst(
    vt_symbol: str,
    as_of: str,
    news_items: list[dict[str, Any]],
    *,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[AnalystReport, RoleResult]:
    user = (
        f"symbol: {vt_symbol}\n"
        f"as_of: {as_of}\n"
        f"headlines: {json.dumps(news_items[:25], default=str)}\n"
    )
    result = _call_role(
        prompts.NEWS_ANALYST_SYSTEM,
        user,
        tier="quick",
        provider=provider,
        model=model,
    )
    report = AnalystReport(
        role="news_analyst",
        summary=result.payload.get("summary", ""),
        evidence=list(result.payload.get("evidence", []) or []),
        confidence=float(result.payload.get("confidence", 0.5) or 0.5),
        rating=parse_rating(result.payload.get("rating")),
    )
    return report, result


def run_technical_analyst(
    vt_symbol: str,
    as_of: str,
    indicators: dict[str, Any],
    *,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[AnalystReport, RoleResult]:
    user = (
        f"symbol: {vt_symbol}\n"
        f"as_of: {as_of}\n"
        f"indicators: {json.dumps(indicators, default=str)}\n"
    )
    result = _call_role(
        prompts.TECHNICAL_ANALYST_SYSTEM,
        user,
        tier="quick",
        provider=provider,
        model=model,
    )
    report = AnalystReport(
        role="technical_analyst",
        summary=result.payload.get("summary", ""),
        evidence=list(result.payload.get("evidence", []) or []),
        confidence=float(result.payload.get("confidence", 0.5) or 0.5),
        rating=parse_rating(result.payload.get("rating")),
    )
    return report, result


# ---------------------------------------------------------------------------
# Bull vs Bear debate
# ---------------------------------------------------------------------------


def _format_reports(reports: list[AnalystReport]) -> str:
    return json.dumps([r.model_dump(mode="json") for r in reports], default=str)


def run_debate_round(
    round_idx: int,
    reports: list[AnalystReport],
    previous_turns: list[DebateTurn],
    *,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[list[DebateTurn], list[RoleResult]]:
    """Run one round of Bull vs Bear.

    Each round emits exactly two turns (bull + bear). Previous turns are
    threaded into the user message so the arguments stay responsive to
    each other.
    """
    prior = [t.model_dump(mode="json") for t in previous_turns]
    user_tmpl = (
        f"analyst_reports: {_format_reports(reports)}\n"
        f"prior_debate_turns: {json.dumps(prior, default=str)}\n"
        f"round: {round_idx}\n"
    )

    bull_result = _call_role(
        prompts.BULL_SYSTEM,
        user_tmpl,
        tier="deep",
        provider=provider,
        model=model,
    )
    bear_result = _call_role(
        prompts.BEAR_SYSTEM,
        user_tmpl,
        tier="deep",
        provider=provider,
        model=model,
    )

    bull_turn = DebateTurn(
        round=round_idx,
        side="bull",
        argument=str(bull_result.payload.get("argument", bull_result.content)),
        cites=list(bull_result.payload.get("cites", []) or []),
        token_cost_usd=bull_result.cost_usd,
    )
    bear_turn = DebateTurn(
        round=round_idx,
        side="bear",
        argument=str(bear_result.payload.get("argument", bear_result.content)),
        cites=list(bear_result.payload.get("cites", []) or []),
        token_cost_usd=bear_result.cost_usd,
    )
    return [bull_turn, bear_turn], [bull_result, bear_result]


# ---------------------------------------------------------------------------
# Trader / Risk / Portfolio Manager
# ---------------------------------------------------------------------------


def run_trader(
    vt_symbol: str,
    reports: list[AnalystReport],
    debate: list[DebateTurn],
    *,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[TraderPlan, RoleResult]:
    user = (
        f"symbol: {vt_symbol}\n"
        f"analyst_reports: {_format_reports(reports)}\n"
        f"debate: {json.dumps([t.model_dump(mode='json') for t in debate], default=str)}\n"
    )
    result = _call_role(
        prompts.TRADER_SYSTEM,
        user,
        tier="deep",
        provider=provider,
        model=model,
    )
    try:
        plan = TraderPlan(
            symbol=vt_symbol,
            proposed_action=result.payload.get("proposed_action", "HOLD"),
            size_pct=float(result.payload.get("size_pct", 0.0) or 0.0),
            horizon_days=int(result.payload.get("horizon_days", 5) or 5),
            rationale=str(result.payload.get("rationale", "")),
        )
    except Exception:
        plan = TraderPlan(symbol=vt_symbol, proposed_action="HOLD", size_pct=0.0)
    return plan, result


def run_risk_manager(
    plan: TraderPlan,
    *,
    max_position_pct: float = 0.20,
    max_daily_loss_pct: float = 0.03,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[RiskVerdict, RoleResult]:
    user = (
        f"trader_plan: {plan.model_dump_json()}\n"
        f"risk_limits: {json.dumps({'max_position_pct': max_position_pct, 'max_daily_loss_pct': max_daily_loss_pct})}\n"
    )
    result = _call_role(
        prompts.RISK_MANAGER_SYSTEM,
        user,
        tier="quick",
        provider=provider,
        model=model,
    )
    try:
        verdict = RiskVerdict(
            approved=bool(result.payload.get("approved", True)),
            adjusted_size_pct=result.payload.get("adjusted_size_pct"),
            reasons=list(result.payload.get("reasons", []) or []),
        )
    except Exception:
        verdict = RiskVerdict(approved=True, reasons=["parse-error; approving by default"])
    # Hard enforce the platform cap even if the LLM forgot.
    capped = min(plan.size_pct, max_position_pct)
    if capped < plan.size_pct and (
        verdict.adjusted_size_pct is None or verdict.adjusted_size_pct > capped
    ):
        verdict.adjusted_size_pct = capped
        verdict.reasons.append(
            f"platform cap enforced: size_pct <= {max_position_pct:.2f}"
        )
    return verdict, result


def run_portfolio_manager(
    plan: TraderPlan,
    verdict: RiskVerdict,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[PortfolioDecision, RoleResult]:
    user = (
        f"trader_plan: {plan.model_dump_json()}\n"
        f"risk_verdict: {verdict.model_dump_json()}\n"
    )
    result = _call_role(
        prompts.PORTFOLIO_MANAGER_SYSTEM,
        user,
        tier="deep",
        provider=provider,
        model=model,
    )
    size_pct = float(result.payload.get("size_pct", plan.size_pct) or 0.0)
    if not verdict.approved:
        size_pct = 0.0
    elif verdict.adjusted_size_pct is not None:
        size_pct = float(verdict.adjusted_size_pct)
    try:
        decision = PortfolioDecision(
            symbol=plan.symbol,
            action=result.payload.get("action", plan.proposed_action.value),
            size_pct=size_pct,
            confidence=float(result.payload.get("confidence", 0.5) or 0.5),
            rating=parse_rating(result.payload.get("rating")),
            rationale=str(result.payload.get("rationale", plan.rationale)),
        )
    except Exception:
        decision = PortfolioDecision(
            symbol=plan.symbol,
            action=plan.proposed_action,
            size_pct=size_pct,
            confidence=0.5,
            rationale=plan.rationale,
        )
    return decision, result


# ---------------------------------------------------------------------------
# CrewAI agent factories (optional parity for live UI runs)
# ---------------------------------------------------------------------------


def make_trading_crewai_agents(llm: Any | None = None) -> dict[str, Any]:
    """Return a dict of CrewAI ``Agent`` instances mirroring the trader crew.

    Used by the Crew Trace page so the user can "watch" a live trader
    crew if they prefer the streaming tool experience. The production
    pipeline calls :func:`aqp.agents.trading.propagate.propagate` which
    uses the direct-LLM functions above.
    """
    from crewai import Agent

    from aqp.agents.tools import get_tool
    from aqp.llm.ollama_client import get_crewai_llm

    deep = llm or get_crewai_llm("deep")
    quick = llm or get_crewai_llm("quick")

    def _tools(names: list[str]):
        return [get_tool(n) for n in names]

    return {
        "fundamentals_analyst": Agent(
            role="Fundamentals Analyst",
            goal="Produce a structured fundamentals report with evidence and a rating.",
            backstory=prompts.FUNDAMENTALS_ANALYST_SYSTEM,
            tools=_tools(["fundamentals_snapshot", "duckdb_query", "normalize_rating"]),
            llm=quick,
            verbose=True,
        ),
        "sentiment_analyst": Agent(
            role="Sentiment Analyst",
            goal="Assess market mood from news sentiment scores.",
            backstory=prompts.SENTIMENT_ANALYST_SYSTEM,
            tools=_tools(["news_digest", "normalize_rating"]),
            llm=quick,
            verbose=True,
        ),
        "news_analyst": Agent(
            role="News Analyst",
            goal="Highlight catalysts and sector headlines.",
            backstory=prompts.NEWS_ANALYST_SYSTEM,
            tools=_tools(["news_digest", "normalize_rating"]),
            llm=quick,
            verbose=True,
        ),
        "technical_analyst": Agent(
            role="Technical Analyst",
            goal="Classify short-term structure via RSI/MACD/Bollinger.",
            backstory=prompts.TECHNICAL_ANALYST_SYSTEM,
            tools=_tools(["technical_snapshot", "duckdb_query"]),
            llm=quick,
            verbose=True,
        ),
        "bull": Agent(
            role="Bull Researcher",
            goal="Argue the strongest long case over a 1-5 day horizon.",
            backstory=prompts.BULL_SYSTEM,
            tools=[],
            llm=deep,
            verbose=True,
        ),
        "bear": Agent(
            role="Bear Researcher",
            goal="Argue the strongest short / avoid case.",
            backstory=prompts.BEAR_SYSTEM,
            tools=[],
            llm=deep,
            verbose=True,
        ),
        "trader": Agent(
            role="Trader",
            goal="Reconcile analysts and debate into one action.",
            backstory=prompts.TRADER_SYSTEM,
            tools=[],
            llm=deep,
            verbose=True,
        ),
        "risk_manager": Agent(
            role="Risk Manager",
            goal="Approve/adjust/reject the trader's plan against platform limits.",
            backstory=prompts.RISK_MANAGER_SYSTEM,
            tools=_tools(["risk_check"]),
            llm=quick,
            verbose=True,
        ),
        "portfolio_manager": Agent(
            role="Portfolio Manager",
            goal="Emit the final AgentDecision.",
            backstory=prompts.PORTFOLIO_MANAGER_SYSTEM,
            tools=[],
            llm=deep,
            verbose=True,
        ),
    }
