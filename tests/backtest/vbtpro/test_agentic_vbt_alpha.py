"""Tests for AgenticVbtAlpha and AgenticOrderModel.

The cache-precompute path is exercised by stubbing the
:class:`DecisionCache` so no real agent runtime is needed.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import pytest

from aqp.agents.trading.types import (
    AgentDecision,
    Rating5,
    TraderAction,
)
from aqp.backtest.vbtpro.signal_builder import SignalArrays
from aqp.core.types import Symbol
from aqp.strategies.vbtpro.agent_order_model import AgenticOrderModel
from aqp.strategies.vbtpro.agentic_alpha import AgenticVbtAlpha, AgenticVbtMode


def _decision(vt: str, ts: datetime, action: TraderAction, size: float) -> AgentDecision:
    rating = Rating5.BUY if action == TraderAction.BUY else (
        Rating5.SELL if action == TraderAction.SELL else Rating5.HOLD
    )
    return AgentDecision(
        vt_symbol=vt,
        timestamp=ts,
        action=action,
        size_pct=size,
        confidence=0.9,
        rating=rating,
    )


class _StubCache:
    def __init__(self, decisions: dict[tuple[str, datetime], AgentDecision]) -> None:
        self._d = decisions
        self.root = "/tmp/stub"

    def get(self, vt_symbol: str, ts: Any) -> AgentDecision | None:
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        return self._d.get((vt_symbol, ts))

    def put(self, decision: AgentDecision) -> None:
        self._d[(decision.vt_symbol, decision.timestamp)] = decision


def test_agentic_vbt_alpha_panel_path_emits_entries() -> None:
    timestamps = pd.date_range("2024-01-01", periods=4)
    bars = pd.DataFrame(
        {
            "timestamp": list(timestamps) * 2,
            "vt_symbol": ["AAPL.NASDAQ"] * 4 + ["MSFT.NASDAQ"] * 4,
            "open": [100] * 4 + [200] * 4,
            "high": [101] * 4 + [201] * 4,
            "low": [99] * 4 + [199] * 4,
            "close": [100] * 4 + [200] * 4,
            "volume": [1e6] * 8,
        }
    )

    decisions = {
        ("AAPL.NASDAQ", timestamps[1].to_pydatetime()): _decision(
            "AAPL.NASDAQ", timestamps[1].to_pydatetime(), TraderAction.BUY, 0.5
        ),
        ("MSFT.NASDAQ", timestamps[2].to_pydatetime()): _decision(
            "MSFT.NASDAQ", timestamps[2].to_pydatetime(), TraderAction.BUY, 0.4
        ),
    }

    alpha = AgenticVbtAlpha(strategy_id="t1", mode=AgenticVbtMode.PRECOMPUTE)
    alpha.cache = _StubCache(decisions)  # type: ignore[assignment]

    arrays = alpha.generate_panel_signals(
        bars,
        universe=[Symbol.parse("AAPL.NASDAQ"), Symbol.parse("MSFT.NASDAQ")],
    )
    assert isinstance(arrays, SignalArrays)
    assert bool(arrays.entries.loc[timestamps[1], "AAPL.NASDAQ"]) is True
    assert bool(arrays.entries.loc[timestamps[2], "MSFT.NASDAQ"]) is True
    assert arrays.size is not None
    assert arrays.size.loc[timestamps[1], "AAPL.NASDAQ"] == pytest.approx(0.5)


def test_agentic_vbt_alpha_skips_below_min_confidence() -> None:
    ts = datetime(2024, 1, 2)
    low_conf = AgentDecision(
        vt_symbol="AAPL.NASDAQ",
        timestamp=ts,
        action=TraderAction.BUY,
        size_pct=0.5,
        confidence=0.1,
        rating=Rating5.BUY,
    )
    alpha = AgenticVbtAlpha(strategy_id="t2", min_confidence=0.5)
    alpha.cache = _StubCache({("AAPL.NASDAQ", ts): low_conf})  # type: ignore[assignment]
    direction, size = alpha._action_to_direction_size(low_conf)
    assert direction is None


def test_agentic_order_model_emits_signed_size() -> None:
    timestamps = pd.date_range("2024-01-01", periods=3)
    close = pd.DataFrame(
        100.0,
        index=timestamps,
        columns=["AAPL.NASDAQ"],
    )
    decisions = {
        ("AAPL.NASDAQ", timestamps[1].to_pydatetime()): _decision(
            "AAPL.NASDAQ", timestamps[1].to_pydatetime(), TraderAction.BUY, 0.6
        ),
    }
    order_model = AgenticOrderModel(strategy_id="o1", size_type="targetpercent")
    order_model.cache = _StubCache(decisions)  # type: ignore[assignment]

    arr = order_model.generate_orders(
        bars=pd.DataFrame(),
        universe=[Symbol.parse("AAPL.NASDAQ")],
        context={"close": close},
    )
    assert arr.size_type == "targetpercent"
    assert arr.size.loc[timestamps[1], "AAPL.NASDAQ"] == pytest.approx(0.6)
    assert arr.size.loc[timestamps[0], "AAPL.NASDAQ"] == 0.0
