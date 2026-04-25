"""Tests for `aqp.agents.trading.types`."""
from __future__ import annotations

from datetime import datetime

from aqp.agents.trading.types import (
    AgentDecision,
    AnalystReport,
    DebateTurn,
    Rating5,
    TraderAction,
    TraderPlan,
    parse_rating,
)


def test_parse_rating_canonical() -> None:
    assert parse_rating("strong_buy") is Rating5.STRONG_BUY
    assert parse_rating("BUY") is Rating5.BUY
    assert parse_rating("Hold") is Rating5.HOLD
    assert parse_rating("sell") is Rating5.SELL
    assert parse_rating("strong sell") is Rating5.STRONG_SELL


def test_parse_rating_heuristics() -> None:
    assert parse_rating("bullish") is Rating5.BUY
    assert parse_rating("bearish") is Rating5.SELL
    assert parse_rating("neutral") is Rating5.HOLD
    assert parse_rating("") is Rating5.HOLD
    assert parse_rating(None) is Rating5.HOLD


def test_rating_numeric_monotonic() -> None:
    assert Rating5.numeric(Rating5.STRONG_SELL) == -2
    assert Rating5.numeric(Rating5.SELL) == -1
    assert Rating5.numeric(Rating5.HOLD) == 0
    assert Rating5.numeric(Rating5.BUY) == 1
    assert Rating5.numeric(Rating5.STRONG_BUY) == 2


def test_trader_action_from_rating() -> None:
    assert TraderAction.from_rating("strong_buy") is TraderAction.BUY
    assert TraderAction.from_rating("buy") is TraderAction.BUY
    assert TraderAction.from_rating(Rating5.HOLD) is TraderAction.HOLD
    assert TraderAction.from_rating(Rating5.SELL) is TraderAction.SELL


def test_analyst_report_coerces_rating() -> None:
    r = AnalystReport(role="x", summary="ok", evidence=[], confidence=0.7, rating="BUY")
    assert r.rating is Rating5.BUY


def test_agent_decision_round_trip() -> None:
    dec = AgentDecision(
        vt_symbol="AAPL.NASDAQ",
        timestamp=datetime(2024, 3, 15),
        action=TraderAction.BUY,
        size_pct=0.2,
        confidence=0.8,
        rating=Rating5.STRONG_BUY,
        rationale="unit test",
        evidence=["e1"],
        analyst_reports=[
            AnalystReport(role="fundamentals_analyst", summary="s", confidence=0.5, rating=Rating5.HOLD)
        ],
        debate_turns=[
            DebateTurn(round=0, side="bull", argument="a"),
            DebateTurn(round=0, side="bear", argument="b"),
        ],
        trader_plan=TraderPlan(symbol="AAPL.NASDAQ", proposed_action=TraderAction.BUY, size_pct=0.2),
    )
    data = dec.model_dump(mode="json")
    assert data["action"] == "BUY"
    assert data["rating"] == "strong_buy"

    restored = AgentDecision.model_validate(data)
    assert restored.action is TraderAction.BUY
    assert restored.rating is Rating5.STRONG_BUY
    assert restored.analyst_reports[0].rating is Rating5.HOLD


def test_agent_decision_hold_helper() -> None:
    d = AgentDecision.hold("AAPL.NASDAQ", datetime(2024, 1, 1))
    assert d.action is TraderAction.HOLD
    assert d.size_pct == 0.0
