"""Tests for FinRobot-style equity research section agents."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from aqp.agents.financial.catalysts import extract_catalysts, normalise_news_sentiment
from aqp.agents.financial.equity_sections import (
    CompanyOverviewAgent,
    InvestmentOverviewAgent,
    MajorTakeawaysAgent,
    NewsSummaryAgent,
    RisksAgent,
    TaglineAgent,
    ValuationOverviewAgent,
)
from aqp.agents.financial.sensitivity import dcf_intrinsic_value, sensitivity_grid


class _FakeCall:
    def __init__(self, payload: dict[str, Any], cost: float = 0.01) -> None:
        self._payload = payload
        self.cost = cost

    def __call__(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "content": "raw",
            "model": "fake-deep",
            "provider": "fake",
            "cost_usd": self.cost,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "payload": self._payload,
        }


def test_tagline_agent_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCall({"text": "Strong earnings growth trajectory.", "highlights": []})
    agent = TaglineAgent(provider="fake", model="m", tier="quick")
    monkeypatch.setattr(agent, "_call", fake)
    rep = agent.run(
        ticker="AAPL.NASDAQ",
        as_of="2024-03-15",
        price_summary={"close": 180.0},
        fundamentals={"revenue": 1000},
        news_digest=[],
        peers=[],
    )
    assert rep.payload["section_key"] == "tagline"
    assert rep.payload["text"].startswith("Strong")


@pytest.mark.parametrize(
    "agent_cls,section_key",
    [
        (CompanyOverviewAgent, "company_overview"),
        (InvestmentOverviewAgent, "investment_overview"),
        (ValuationOverviewAgent, "valuation_overview"),
        (RisksAgent, "risks"),
        (NewsSummaryAgent, "news_summary"),
        (MajorTakeawaysAgent, "major_takeaways"),
    ],
)
def test_each_section_agent_returns_payload(
    monkeypatch: pytest.MonkeyPatch,
    agent_cls,
    section_key: str,
) -> None:
    payload = {
        "text": f"{section_key} body",
        "highlights": ["hi 1", "hi 2"],
    }
    fake = _FakeCall(payload)
    agent = agent_cls(provider="fake", model="m")
    monkeypatch.setattr(agent, "_call", fake)
    rep = agent.run(
        ticker="MSFT.NASDAQ",
        as_of="2024-03-15",
        price_summary={"close": 400.0},
        fundamentals={},
        news_digest=[{"title": "Microsoft beats on cloud"}],
        peers=["GOOGL.NASDAQ"],
        extras={
            "section_summaries": {"tagline": "great quarter"},
            "valuation_inputs": {"free_cash_flow_t0": 100},
            "peer_fundamentals": {},
        },
    )
    assert rep.payload["section_key"] == section_key
    assert rep.payload["text"] == f"{section_key} body"
    assert "hi 1" in rep.payload["highlights"]


def test_dcf_intrinsic_value_basic() -> None:
    out = dcf_intrinsic_value(
        free_cash_flow_t0=100.0,
        growth_rate=0.05,
        terminal_growth=0.025,
        discount_rate=0.08,
        horizon_years=5,
        shares_outstanding=100.0,
        net_debt=0.0,
    )
    assert out["enterprise_value"] > 0
    assert out["per_share"] > 0


def test_sensitivity_grid_cells() -> None:
    grid = sensitivity_grid(
        free_cash_flow_t0=100.0,
        base_growth=0.05,
        base_discount=0.08,
        terminal_growth=0.025,
        horizon_years=5,
        shares_outstanding=100.0,
    )
    assert grid["cells"], "expected non-empty grid"
    # All values are non-negative or None (when discount <= terminal).
    for cell in grid["cells"]:
        if cell["value"] is not None:
            assert cell["value"] > 0


def test_extract_catalysts_returns_kinds() -> None:
    news = [
        {"title": "Quarterly earnings beat estimates", "summary": "..."},
        {"title": "FDA approves new drug application", "summary": "..."},
        {"title": "Generic article", "summary": "Nothing actionable"},
    ]
    catalysts = extract_catalysts(news=news)
    kinds = {c["kind"] for c in catalysts}
    assert "earnings" in kinds or "regulatory" in kinds


def test_normalise_news_sentiment_counts() -> None:
    news = [
        {"title": "stock surges as company beats"},
        {"title": "outlook cut after miss"},
        {"title": "neutral note"},
    ]
    sent = normalise_news_sentiment(news)
    assert sent["n"] == 3
    assert sent["pos"] >= 1
