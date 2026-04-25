"""AgenticAlpha integration tests (cache-only mode, no LLM)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aqp.agents.trading.decision_cache import DecisionCache
from aqp.agents.trading.types import AgentDecision, Rating5, TraderAction
from aqp.core.types import Direction, Symbol
from aqp.strategies.agentic.agentic_alpha import AgenticAlpha, AgenticAlphaMode


def _seed_cache(tmp_path: Path, sid: str, vt: str, ts: datetime, action: TraderAction) -> None:
    cache = DecisionCache(root=tmp_path, strategy_id=sid)
    cache.put(
        AgentDecision(
            vt_symbol=vt,
            timestamp=ts,
            action=action,
            size_pct=0.2,
            confidence=0.8,
            rating=Rating5.BUY if action is TraderAction.BUY else Rating5.HOLD,
            rationale="unit test",
            context_hash="abc",
        )
    )


def test_agentic_alpha_emits_buy_signal(tmp_path: Path) -> None:
    sid = "alpha-test-buy"
    ts = datetime(2024, 3, 15)
    _seed_cache(tmp_path, sid, "AAPL.NASDAQ", ts, TraderAction.BUY)

    alpha = AgenticAlpha(
        strategy_id=sid,
        cache_root=str(tmp_path),
        mode=AgenticAlphaMode.PRECOMPUTE,
    )
    sym = Symbol.parse("AAPL.NASDAQ")
    signals = alpha.generate_signals(
        bars=None,  # unused when context carries the timestamp
        universe=[sym],
        context={"current_time": ts},
    )
    assert len(signals) == 1
    sig = signals[0]
    assert sig.direction is Direction.LONG
    assert sig.strength == 0.2


def test_agentic_alpha_skips_hold(tmp_path: Path) -> None:
    sid = "alpha-test-hold"
    ts = datetime(2024, 3, 15)
    _seed_cache(tmp_path, sid, "AAPL.NASDAQ", ts, TraderAction.HOLD)

    alpha = AgenticAlpha(
        strategy_id=sid,
        cache_root=str(tmp_path),
        mode=AgenticAlphaMode.PRECOMPUTE,
    )
    sym = Symbol.parse("AAPL.NASDAQ")
    signals = alpha.generate_signals(
        bars=None,
        universe=[sym],
        context={"current_time": ts},
    )
    assert signals == []
    assert alpha.stats["hold_skips"] == 1


def test_agentic_alpha_miss_records_stat(tmp_path: Path) -> None:
    sid = "alpha-test-miss"
    ts = datetime(2024, 3, 15)

    alpha = AgenticAlpha(
        strategy_id=sid,
        cache_root=str(tmp_path),
        mode=AgenticAlphaMode.PRECOMPUTE,
    )
    sym = Symbol.parse("AAPL.NASDAQ")
    signals = alpha.generate_signals(
        bars=None,
        universe=[sym],
        context={"current_time": ts},
    )
    assert signals == []
    assert alpha.stats["misses"] == 1
    assert alpha.hit_rate() == 0.0


def test_agentic_alpha_rating_size_map(tmp_path: Path) -> None:
    sid = "alpha-test-map"
    ts = datetime(2024, 3, 15)
    _seed_cache(tmp_path, sid, "AAPL.NASDAQ", ts, TraderAction.BUY)

    alpha = AgenticAlpha(
        strategy_id=sid,
        cache_root=str(tmp_path),
        mode=AgenticAlphaMode.PRECOMPUTE,
        rating_size_map={"buy": 0.5, "strong_buy": 1.0},
    )
    sym = Symbol.parse("AAPL.NASDAQ")
    signals = alpha.generate_signals(
        bars=None,
        universe=[sym],
        context={"current_time": ts},
    )
    assert len(signals) == 1
    # Our seeded decision is Rating5.BUY → rating_size_map says 0.5.
    assert signals[0].strength == 0.5
