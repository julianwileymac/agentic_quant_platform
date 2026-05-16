"""Tests for :class:`aqp.strategies.hft.microprice.MicropriceAlpha`."""
from __future__ import annotations

from datetime import datetime

from aqp.strategies.hft.microprice import MicropriceAlpha
from aqp.strategies.lob import LobState


def _state(
    bid: float,
    ask: float,
    bid_qty: float,
    ask_qty: float,
    position: float = 0.0,
) -> LobState:
    return LobState(
        timestamp=datetime(2024, 1, 1, 9, 30, 0),
        asset_no=0,
        best_bid=bid,
        best_ask=ask,
        bid_qty=bid_qty,
        ask_qty=ask_qty,
        position=position,
        cash=0.0,
    )


def test_registry_entry() -> None:
    from aqp.core.registry import resolve

    assert resolve("MicropriceAlpha") is MicropriceAlpha


def test_below_threshold_no_signal() -> None:
    alpha = MicropriceAlpha(threshold_bps=10.0, cooldown_events=0)
    # Symmetric book — microprice == mid.
    intents = alpha.on_event(_state(100.0, 100.1, 10.0, 10.0))
    assert intents == []


def test_microprice_above_mid_fires_long() -> None:
    alpha = MicropriceAlpha(threshold_bps=0.5, cooldown_events=0, order_size=2.0)
    # Heavy bid queue pulls microprice toward ask.
    intents = alpha.on_event(_state(100.0, 100.1, 100.0, 1.0))
    assert len(intents) == 1
    assert intents[0].side == "buy"
    assert intents[0].tag == "microprice_long"


def test_microprice_below_mid_fires_short() -> None:
    alpha = MicropriceAlpha(threshold_bps=0.5, cooldown_events=0)
    intents = alpha.on_event(_state(100.0, 100.1, 1.0, 100.0))
    assert len(intents) == 1
    assert intents[0].side == "sell"
    assert intents[0].tag == "microprice_short"


def test_cooldown_blocks_rapid_fire() -> None:
    alpha = MicropriceAlpha(threshold_bps=0.5, cooldown_events=5)
    first = alpha.on_event(_state(100.0, 100.1, 100.0, 1.0))
    assert len(first) == 1
    # Next few events must be empty regardless of signal strength.
    for _ in range(4):
        intents = alpha.on_event(_state(100.0, 100.1, 100.0, 1.0))
        assert intents == []
    # 6th event (cooldown_events + 1) should fire again.
    intents = alpha.on_event(_state(100.0, 100.1, 100.0, 1.0))
    assert len(intents) == 1


def test_position_cap_blocks_signal() -> None:
    alpha = MicropriceAlpha(threshold_bps=0.5, cooldown_events=0, max_position=1.0)
    intents = alpha.on_event(
        _state(100.0, 100.1, 100.0, 1.0, position=1.0),
    )
    assert intents == []


def test_zero_prices_returns_empty() -> None:
    alpha = MicropriceAlpha(threshold_bps=0.5, cooldown_events=0)
    intents = alpha.on_event(_state(0.0, 0.0, 100.0, 1.0))
    assert intents == []
