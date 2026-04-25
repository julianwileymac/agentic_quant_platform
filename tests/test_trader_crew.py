"""Smoke tests for the trader crew (with mocked LLM router)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from aqp.agents.trading import crew as crew_mod
from aqp.agents.trading.crew import TraderCrewConfig
from aqp.agents.trading.types import Rating5, TraderAction


class _FakeLLMResult:
    def __init__(self, content: str) -> None:
        self.content = content
        self.model = "test-model"
        self.provider = "test"
        self.prompt_tokens = 10
        self.completion_tokens = 5
        self.cost_usd = 0.0001


def _fake_complete(tier: str, messages=None, prompt=None, **kw: Any):  # noqa: ARG001
    system = (messages or [{}])[0].get("content", "")
    if "FUNDAMENTALS ANALYST" in system:
        body = '{"summary": "solid", "evidence": ["fcf up"], "confidence": 0.8, "rating": "buy"}'
    elif "SENTIMENT ANALYST" in system:
        body = '{"summary": "positive mood", "evidence": [], "confidence": 0.6, "rating": "buy"}'
    elif "NEWS ANALYST" in system:
        body = '{"summary": "catalysts ahead", "evidence": [], "confidence": 0.7, "rating": "buy"}'
    elif "TECHNICAL ANALYST" in system:
        body = '{"summary": "trending up", "evidence": ["breakout"], "confidence": 0.65, "rating": "buy"}'
    elif "BULL RESEARCHER" in system:
        body = '{"argument": "long case", "cites": ["fcf up"]}'
    elif "BEAR RESEARCHER" in system:
        body = '{"argument": "bearish tape", "cites": []}'
    elif "TRADER" in system:
        body = (
            '{"proposed_action": "BUY", "size_pct": 0.15, "horizon_days": 5, '
            '"rationale": "analysts converge bullish"}'
        )
    elif "RISK MANAGER" in system:
        body = '{"approved": true, "adjusted_size_pct": 0.1, "reasons": ["cap"]}'
    elif "PORTFOLIO MANAGER" in system:
        body = (
            '{"action": "BUY", "size_pct": 0.1, "confidence": 0.75, '
            '"rating": "buy", "rationale": "risk-adjusted buy"}'
        )
    else:
        body = "{}"
    return _FakeLLMResult(body)


def test_run_trader_crew_produces_decision(monkeypatch) -> None:
    # Stub every outside dependency (LLM + tool data) so the test is hermetic.
    monkeypatch.setattr(
        "aqp.agents.trading.roles.complete",
        _fake_complete,
    )
    monkeypatch.setattr(
        crew_mod,
        "_gather_context",
        lambda vt, ts, cfg: ({"trailingPE": 30.0}, {"rsi_14": 55, "close": 180}, []),
    )

    cfg = TraderCrewConfig(
        name="unit",
        max_debate_rounds=1,
        provider="test",
        deep_model="test-model",
        quick_model="test-model",
        include_fundamentals=True,
        include_sentiment=True,
        include_news=True,
        include_technical=True,
    )
    decision = crew_mod.run_trader_crew(
        "AAPL.NASDAQ",
        datetime(2024, 3, 15),
        cfg,
    )
    assert decision.action is TraderAction.BUY
    assert decision.rating is Rating5.BUY
    # Risk manager adjusted the size to 0.1 (cap) and PM honoured it.
    assert decision.size_pct == 0.1
    # Four analysts + 2 debate + trader + risk + PM = 9 LLM calls; each
    # has cost_usd=0.0001 in the stub.
    assert decision.token_cost_usd > 0
    assert len(decision.analyst_reports) == 4
    assert len(decision.debate_turns) == 2
    assert decision.trader_plan is not None
    assert decision.risk_verdict is not None
