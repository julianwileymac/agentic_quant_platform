"""Smart Scheduler — route LLM calls by agent role.

Inspired by FinRobot's "Smart Scheduler" pattern: classifier-style
roles (regime detection, hypothesis screening, sentiment scoring)
don't need a 70B+ deep-tier model; synthesis-style roles (portfolio
manager debate, parameter mutation, trade rationale) benefit from
the largest model the deployment supports.

This module exposes a single helper, :func:`pick_tier_for_role`,
that maps an agent role/kind string to ``"deep"`` or ``"quick"``.
:mod:`aqp.agents.runtime` calls it when a spec doesn't set
``model.tier`` explicitly. Existing specs that already set the tier
(every AgentSpec yaml in ``configs/agents/``) are unaffected.

The mapping is intentionally narrow — adding a role doesn't require
a code change because every unknown role falls through to ``"deep"``
(the conservative default that matches today's behaviour).
"""
from __future__ import annotations

from typing import Literal

Tier = Literal["quick", "deep"]


# Roles that benefit from the larger / slower model. Synthesis,
# debate, multi-step reasoning, anything that consumes a long context
# of structured evidence and produces a calibrated verdict.
_DEEP_ROLES: frozenset[str] = frozenset(
    {
        "portfolio_manager",
        "bull_researcher",
        "bear_researcher",
        "parameter_mutator",
        "risk_simulator",
        "quant_generator",
        "analysis.run",
        "analysis.portfolio",
        "trader.signal_emitter",
        "agent_runtime",
    }
)


# Roles where speed + low cost beat marginal accuracy. Classification,
# screening, sentiment polarity, regime detection — these tend to be
# short single-shot calls where a 7B-class model is good enough.
_QUICK_ROLES: frozenset[str] = frozenset(
    {
        "regime_classifier",
        "regime_analyst",
        "market_monitor",
        "news_classifier",
        "sentiment_scorer",
        "universe_screener",
        "composite_voter",
        "dataset_loading_assistant",
    }
)


def pick_tier_for_role(role: str | None, default: Tier = "deep") -> Tier:
    """Return the model tier suited to *role*.

    Falls back to *default* (``"deep"``) for unrecognised roles so the
    Scheduler never silently downgrades an unknown agent.
    """
    if not role:
        return default
    key = role.strip().lower()
    if key in _QUICK_ROLES:
        return "quick"
    if key in _DEEP_ROLES:
        return "deep"
    # Heuristic for roles that follow a naming convention.
    if any(token in key for token in ("classifier", "screener", "monitor", "scorer", "polarity")):
        return "quick"
    if any(token in key for token in ("synthesizer", "manager", "debate", "researcher", "generator")):
        return "deep"
    return default


__all__ = ["Tier", "pick_tier_for_role"]
