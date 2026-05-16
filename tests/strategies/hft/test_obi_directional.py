"""Tests for :class:`aqp.strategies.hft.obi_directional.OBIDirectionalAlpha`.

Hermetic — no network, no Iceberg, no LLM. Synthesises ``LobState``
snapshots and asserts on the emitted :class:`OrderIntent` shape /
direction.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from aqp.strategies.hft.obi_directional import OBIDirectionalAlpha
from aqp.strategies.lob import LobState


def _state(bid: float, ask: float, bid_qty: float, ask_qty: float, position: float = 0.0) -> LobState:
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

    cls = resolve("OBIDirectionalAlpha")
    assert cls is OBIDirectionalAlpha


def test_no_signal_during_warmup() -> None:
    alpha = OBIDirectionalAlpha(window=8, enter_z=1.5)
    # First few events: not enough samples for a meaningful z-score.
    for _ in range(3):
        intents = alpha.on_event(_state(100.0, 100.1, 5.0, 5.0))
        assert intents == []


def test_positive_imbalance_fires_long() -> None:
    alpha = OBIDirectionalAlpha(window=16, enter_z=1.0, exit_z=0.2, order_size=2.0)
    # Seed history with neutral imbalances.
    for _ in range(16):
        alpha.on_event(_state(100.0, 100.1, 5.0, 5.0))
    # Now a strongly bid-heavy snapshot should trip the long threshold.
    intents = alpha.on_event(_state(100.0, 100.1, 50.0, 1.0))
    assert len(intents) == 1
    intent = intents[0]
    assert intent.side == "buy"
    assert intent.quantity == 2.0
    assert intent.order_type == "market"
    assert intent.tag == "obi_long"


def test_negative_imbalance_fires_short() -> None:
    alpha = OBIDirectionalAlpha(window=16, enter_z=1.0, exit_z=0.2)
    for _ in range(16):
        alpha.on_event(_state(100.0, 100.1, 5.0, 5.0))
    intents = alpha.on_event(_state(100.0, 100.1, 1.0, 50.0))
    assert len(intents) == 1
    assert intents[0].side == "sell"
    assert intents[0].tag == "obi_short"


def test_position_cap_blocks_further_buys() -> None:
    alpha = OBIDirectionalAlpha(window=8, enter_z=0.5, exit_z=0.2, max_position=1.0)
    for _ in range(8):
        alpha.on_event(_state(100.0, 100.1, 5.0, 5.0))
    intents = alpha.on_event(_state(100.0, 100.1, 50.0, 1.0, position=1.0))
    assert intents == []


def test_exit_flattens_position() -> None:
    alpha = OBIDirectionalAlpha(window=8, enter_z=1.0, exit_z=0.4, order_size=2.0)
    # Build a baseline + push imbalance back near zero with non-zero position.
    for _ in range(8):
        alpha.on_event(_state(100.0, 100.1, 5.0, 5.0))
    intents = alpha.on_event(_state(100.0, 100.1, 5.0, 5.0, position=3.0))
    assert any(i.tag == "obi_exit" and i.side == "sell" for i in intents)


def test_microprice_edge_filter_blocks_low_edge_signals() -> None:
    alpha = OBIDirectionalAlpha(
        window=8, enter_z=0.5, exit_z=0.2, microprice_edge_bps=10.0
    )
    for _ in range(8):
        alpha.on_event(_state(100.0, 100.1, 5.0, 5.0))
    # Mild imbalance — microprice is mid + ~0.5bps, well below 10bps.
    intents = alpha.on_event(_state(100.0, 100.1, 8.0, 4.0))
    assert intents == []


def test_microprice_edge_filter_allows_strong_edge_signals() -> None:
    alpha = OBIDirectionalAlpha(
        window=8, enter_z=0.5, exit_z=0.2, microprice_edge_bps=0.1
    )
    for _ in range(8):
        alpha.on_event(_state(100.0, 100.1, 5.0, 5.0))
    intents = alpha.on_event(_state(100.0, 100.1, 100.0, 1.0))
    assert any(i.side == "buy" for i in intents)
