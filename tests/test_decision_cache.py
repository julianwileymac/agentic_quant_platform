"""Tests for the decision cache."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from aqp.agents.trading.decision_cache import DecisionCache
from aqp.agents.trading.types import AgentDecision, Rating5, TraderAction


def _make_decision(vt: str, ts: datetime, *, action: TraderAction = TraderAction.BUY) -> AgentDecision:
    return AgentDecision(
        vt_symbol=vt,
        timestamp=ts,
        action=action,
        size_pct=0.15,
        confidence=0.8,
        rating=Rating5.BUY,
        rationale="unit test",
        provider="openai",
        deep_model="gpt-5.4",
        quick_model="gpt-5.4-mini",
        token_cost_usd=0.01,
        context_hash="abc123def456",
    )


def test_put_and_get_round_trip(tmp_path: Path) -> None:
    cache = DecisionCache(root=tmp_path, strategy_id="unit-test")
    ts = datetime(2024, 3, 15)
    d = _make_decision("AAPL.NASDAQ", ts)
    path = cache.put(d)
    assert path.exists()

    out = cache.get("AAPL.NASDAQ", ts)
    assert out is not None
    assert out.action is TraderAction.BUY
    assert out.rationale == "unit test"
    assert out.context_hash == "abc123def456"


def test_get_by_hash(tmp_path: Path) -> None:
    cache = DecisionCache(root=tmp_path, strategy_id="unit-test")
    ts = datetime(2024, 3, 15)
    d = _make_decision("AAPL.NASDAQ", ts)
    cache.put(d)
    hit = cache.get_by_hash("AAPL.NASDAQ", ts, "abc123def456")
    miss = cache.get_by_hash("AAPL.NASDAQ", ts, "nohash")
    assert hit is not None
    assert miss is None


def test_scan_filters_by_symbol_and_date(tmp_path: Path) -> None:
    cache = DecisionCache(root=tmp_path, strategy_id="unit-test")
    t0 = datetime(2024, 3, 1)
    for i, sym in enumerate(["AAPL.NASDAQ", "MSFT.NASDAQ", "GOOGL.NASDAQ"]):
        cache.put(_make_decision(sym, t0 + timedelta(days=i)))

    df_all = cache.scan()
    assert len(df_all) == 3

    df_apple = cache.scan(vt_symbols=["AAPL.NASDAQ"])
    assert len(df_apple) == 1
    assert df_apple.iloc[0]["vt_symbol"] == "AAPL.NASDAQ"

    df_window = cache.scan(start=t0, end=t0 + timedelta(days=1))
    assert len(df_window) == 2


def test_bulk_precompute_uses_cache(tmp_path: Path, monkeypatch) -> None:
    cache = DecisionCache(root=tmp_path, strategy_id="unit-test")
    calls = {"n": 0}

    def fake_propagate(sym, ts, *, config=None, cache=None, force=False, **_):  # noqa: ARG001
        calls["n"] += 1
        decision = _make_decision(sym, ts)
        if cache is not None:
            cache.put(decision)
        return decision

    # Reach the submodule via sys.modules — robust to the trading-package
    # ``__init__`` re-exporting ``propagate`` (which shadows the submodule
    # attribute in normal import syntax).
    import sys

    # Force the submodule to be loaded.
    import aqp.agents.trading.propagate  # noqa: F401
    prop_mod = sys.modules["aqp.agents.trading.propagate"]

    monkeypatch.setattr(prop_mod, "propagate", fake_propagate)

    symbols = ["AAPL.NASDAQ", "MSFT.NASDAQ"]
    dates = [datetime(2024, 3, 15), datetime(2024, 3, 22)]
    decisions = cache.bulk_precompute(symbols=symbols, dates=dates, config=None)
    assert len(decisions) == 4
    # Underlying propagate was called 4 times (2 symbols × 2 dates).
    assert calls["n"] == 4


def test_total_cost(tmp_path: Path) -> None:
    cache = DecisionCache(root=tmp_path, strategy_id="unit-test")
    cache.put(_make_decision("AAPL.NASDAQ", datetime(2024, 3, 1)))
    cache.put(_make_decision("MSFT.NASDAQ", datetime(2024, 3, 2)))
    assert cache.total_cost_usd() == pytest.approx(0.02, rel=1e-6)
