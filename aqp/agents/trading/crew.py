"""Trader-crew orchestrator.

Wires the role functions in :mod:`aqp.agents.trading.roles` into a
deterministic pipeline:

1. Fetch fundamentals + news + technical snapshots (local tools).
2. Run each analyst role once.
3. Run ``max_debate_rounds`` of Bull vs Bear.
4. Trader → Risk Manager → Portfolio Manager.

Returns a complete :class:`AgentDecision` with analyst reports, debate
turns, trader plan, risk verdict, and portfolio decision embedded for
full traceability.

This module is used by both :func:`aqp.agents.trading.propagate.propagate`
(single symbol + date) and the Celery ``precompute_decisions`` task
(bulk over a range).
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from aqp.agents.trading import roles
from aqp.agents.trading.types import (
    AgentDecision,
    AnalystReport,
    DebateTurn,
    PortfolioDecision,
    Rating5,
    RiskVerdict,
    TraderAction,
    TraderPlan,
)
from aqp.config import settings

logger = logging.getLogger(__name__)


DEFAULT_PRESET_DIR = Path(__file__).resolve().parent.parent.parent.parent / "configs" / "agents"


@dataclass
class TraderCrewConfig:
    """Declarative configuration for one crew run.

    Matches the YAML shape in ``configs/agents/trader_crew*.yaml``.
    """

    name: str = "trader_crew"
    max_debate_rounds: int = 1
    provider: str = ""  # "" means use settings.llm_provider
    deep_model: str = ""
    quick_model: str = ""
    risk_max_position_pct: float = 0.20
    risk_max_daily_loss_pct: float = 0.03
    include_fundamentals: bool = True
    include_sentiment: bool = True
    include_news: bool = True
    include_technical: bool = True
    news_lookback_days: int = 7
    technical_lookback_days: int = 120
    extras: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "TraderCrewConfig":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        clean = {k: v for k, v in data.items() if k in known}
        extras = {k: v for k, v in data.items() if k not in known}
        clean["extras"] = extras
        return cls(**clean)

    @classmethod
    def from_preset(cls, preset: str) -> "TraderCrewConfig":
        """Load a named preset from ``configs/agents/<preset>.yaml``."""
        path = DEFAULT_PRESET_DIR / f"{preset}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Unknown trader crew preset: {preset} (expected {path})")
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return cls.from_dict(data)


def _context_hash(
    vt_symbol: str,
    as_of: str,
    cfg: TraderCrewConfig,
    fundamentals: dict,
    technical: dict,
    news_ids: list[str],
) -> str:
    payload = {
        "symbol": vt_symbol,
        "as_of": as_of,
        "cfg": {
            "name": cfg.name,
            "max_debate_rounds": cfg.max_debate_rounds,
            "provider": cfg.provider,
            "deep_model": cfg.deep_model,
            "quick_model": cfg.quick_model,
        },
        "fundamentals": fundamentals,
        "technical": technical,
        "news_ids": news_ids,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def _gather_context(
    vt_symbol: str,
    as_of: str,
    cfg: TraderCrewConfig,
) -> tuple[dict, dict, list[dict]]:
    """Call the local tools (no LLM here) to assemble analyst inputs."""
    fundamentals: dict = {}
    if cfg.include_fundamentals:
        try:
            from aqp.agents.tools.fundamentals_tool import compute_fundamentals_snapshot

            fundamentals = compute_fundamentals_snapshot(vt_symbol, as_of)
        except Exception as exc:
            logger.info("fundamentals unavailable for %s: %s", vt_symbol, exc)

    technical: dict = {}
    if cfg.include_technical:
        try:
            from aqp.agents.tools.technical_tool import compute_technical_snapshot

            technical = compute_technical_snapshot(
                vt_symbol,
                as_of=as_of,
                lookback_days=cfg.technical_lookback_days,
            )
        except Exception as exc:
            logger.info("technical snapshot failed for %s: %s", vt_symbol, exc)

    news_items: list[dict] = []
    if cfg.include_news or cfg.include_sentiment:
        try:
            from aqp.agents.tools.news_tool import fetch_news_items, score_items

            news_items = fetch_news_items(
                vt_symbol,
                as_of=as_of,
                lookback_days=cfg.news_lookback_days,
            )
            if news_items and cfg.include_sentiment:
                news_items = score_items(news_items)
        except Exception as exc:
            logger.info("news digest failed for %s: %s", vt_symbol, exc)

    return fundamentals, technical, news_items


def run_trader_crew(
    vt_symbol: str,
    as_of: datetime | str,
    cfg: TraderCrewConfig | None = None,
    *,
    crew_run_id: str | None = None,
    capabilities: dict | None = None,
) -> AgentDecision:
    """Run the full trader crew for one ``(symbol, as_of)`` and return a decision.

    Heavy lifting:

    - Gather local tool snapshots (no LLM).
    - Run each analyst in parallel (simple serial loop today; swap in
      ``asyncio.gather`` when we async-ify the router).
    - Run ``cfg.max_debate_rounds`` of Bull/Bear.
    - Trader → Risk → PM.

    Optional ``capabilities`` is a dict matching :class:`AgentCapabilities`;
    when provided we instantiate :class:`CapabilityRuntime` to gate
    each role's cost + structured-output checks.
    """
    if cfg is None:
        cfg = TraderCrewConfig.from_preset(settings.agentic_default_preset)
    if capabilities is None:
        capabilities = (cfg.extras or {}).get("capabilities") if cfg else None
    runtime = None
    if capabilities:
        try:
            from aqp.agents.capabilities import AgentCapabilities
            from aqp.agents.capability_runtime import CapabilityRuntime, GuardrailViolation

            runtime = CapabilityRuntime(AgentCapabilities(**capabilities))
            logger.info(
                "trader crew capabilities active: %s",
                runtime.stats(),
            )
        except Exception:
            logger.exception("trader crew: capability runtime init failed; continuing without")
            runtime = None

    if isinstance(as_of, datetime):
        as_of_iso = as_of.isoformat()
    else:
        as_of_iso = str(as_of)
    as_of_dt = datetime.fromisoformat(as_of_iso) if isinstance(as_of, str) else as_of

    provider = cfg.provider or settings.llm_provider
    deep_model = cfg.deep_model or settings.llm_deep_model
    quick_model = cfg.quick_model or settings.llm_quick_model

    fundamentals, technical, news_items = _gather_context(vt_symbol, as_of_iso, cfg)
    news_ids = [str(it.get("id") or it.get("uuid") or "") for it in news_items]

    context_hash = _context_hash(
        vt_symbol, as_of_iso, cfg, fundamentals, technical, news_ids
    )

    reports: list[AnalystReport] = []
    running_cost = 0.0

    # Analysts
    if cfg.include_fundamentals:
        rep, res = roles.run_fundamentals_analyst(
            vt_symbol, as_of_iso, fundamentals,
            provider=provider, model=quick_model,
        )
        reports.append(rep)
        running_cost += res.cost_usd

    if cfg.include_sentiment:
        rep, res = roles.run_sentiment_analyst(
            vt_symbol, as_of_iso, news_items,
            provider=provider, model=quick_model,
        )
        reports.append(rep)
        running_cost += res.cost_usd

    if cfg.include_news:
        rep, res = roles.run_news_analyst(
            vt_symbol, as_of_iso, news_items,
            provider=provider, model=quick_model,
        )
        reports.append(rep)
        running_cost += res.cost_usd

    if cfg.include_technical:
        rep, res = roles.run_technical_analyst(
            vt_symbol, as_of_iso, technical,
            provider=provider, model=quick_model,
        )
        reports.append(rep)
        running_cost += res.cost_usd

    # Bull / Bear debate rounds
    debate: list[DebateTurn] = []
    for round_idx in range(max(0, int(cfg.max_debate_rounds))):
        turns, turn_results = roles.run_debate_round(
            round_idx, reports, debate,
            provider=provider, model=deep_model,
        )
        debate.extend(turns)
        for rr in turn_results:
            running_cost += rr.cost_usd

    # Trader
    plan, trader_res = roles.run_trader(
        vt_symbol, reports, debate,
        provider=provider, model=deep_model,
    )
    running_cost += trader_res.cost_usd

    # Risk Manager
    verdict, risk_res = roles.run_risk_manager(
        plan,
        max_position_pct=cfg.risk_max_position_pct,
        max_daily_loss_pct=cfg.risk_max_daily_loss_pct,
        provider=provider,
        model=quick_model,
    )
    running_cost += risk_res.cost_usd

    # Portfolio Manager
    decision, pm_res = roles.run_portfolio_manager(
        plan, verdict,
        provider=provider, model=deep_model,
    )
    running_cost += pm_res.cost_usd

    action = decision.action if isinstance(decision.action, TraderAction) else TraderAction(decision.action)

    # Capability post-validation: surface guardrail violations as a
    # neutral HOLD with the violation captured in the rationale instead
    # of crashing the bulk-precompute loop.
    if runtime is not None:
        try:
            payload = {
                "vt_symbol": vt_symbol,
                "action": str(action),
                "size_pct": float(decision.size_pct),
                "confidence": float(decision.confidence),
                "rating": decision.rating.value if hasattr(decision.rating, "value") else str(decision.rating),
                "rationale": decision.rationale or "",
            }
            runtime.validate_output(payload)
            runtime.track_call(cost_usd=running_cost)
        except Exception as exc:
            logger.warning(
                "trader crew capability check failed for %s @ %s: %s",
                vt_symbol,
                as_of_iso,
                exc,
            )
            return AgentDecision.hold(
                vt_symbol=vt_symbol,
                timestamp=as_of_dt,
                rationale=f"guardrail rejected output: {exc}",
            )

    return AgentDecision(
        vt_symbol=vt_symbol,
        timestamp=as_of_dt,
        action=action,
        size_pct=max(0.0, min(1.0, float(decision.size_pct))),
        confidence=max(0.0, min(1.0, float(decision.confidence))),
        rating=decision.rating if isinstance(decision.rating, Rating5) else Rating5(decision.rating),
        rationale=decision.rationale,
        evidence=[e for r in reports for e in r.evidence[:3]],
        crew_run_id=crew_run_id or str(uuid.uuid4()),
        provider=provider,
        deep_model=deep_model,
        quick_model=quick_model,
        token_cost_usd=round(running_cost, 6),
        context_hash=context_hash,
        analyst_reports=reports,
        debate_turns=debate,
        trader_plan=plan,
        risk_verdict=verdict,
    )


def build_trader_crew_config(
    preset: str | None = None,
    overrides: dict | None = None,
) -> TraderCrewConfig:
    """Helper used by the API + wizard to combine a preset with UI overrides."""
    if preset:
        cfg = TraderCrewConfig.from_preset(preset)
    else:
        cfg = TraderCrewConfig.from_preset(settings.agentic_default_preset)
    if overrides:
        for k, v in overrides.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
            else:
                cfg.extras[k] = v
    return cfg
