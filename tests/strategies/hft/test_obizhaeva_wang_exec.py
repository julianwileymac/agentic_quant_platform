"""Tests for :class:`ObizhaevaWangExecution` `LobStrategy`."""
from __future__ import annotations

from datetime import datetime, timedelta

from aqp.strategies.hft.obizhaeva_wang_exec import ObizhaevaWangExecution
from aqp.strategies.lob import LobState


def _state(timestamp: datetime, position: float = 0.0) -> LobState:
    return LobState(
        timestamp=timestamp,
        asset_no=0,
        best_bid=100.0,
        best_ask=100.1,
        bid_qty=10.0,
        ask_qty=10.0,
        position=position,
        cash=0.0,
    )


def test_initial_event_fires_initial_chunk() -> None:
    strat = ObizhaevaWangExecution(
        total_shares=10.0, horizon_seconds=10.0, resilience=1.0, impact_coeff=1.0
    )
    t0 = datetime(2024, 1, 1)
    intents = strat.on_event(_state(t0))
    assert len(intents) == 1
    assert intents[0].tag == "ow_initial"
    assert intents[0].side == "buy"
    # X / (2 + rho*T) = 10 / 12 ≈ 0.833
    assert 0.5 < intents[0].quantity < 1.0


def test_terminal_event_fires_remainder_at_horizon() -> None:
    strat = ObizhaevaWangExecution(
        total_shares=10.0,
        horizon_seconds=10.0,
        resilience=1.0,
        impact_coeff=1.0,
        tick_quantity=10.0,  # large tick so continuous phase fires fast
    )
    t0 = datetime(2024, 1, 1)
    # Initial chunk.
    strat.on_event(_state(t0))
    # Advance halfway through the horizon — continuous phase emits.
    strat.on_event(_state(t0 + timedelta(seconds=5.0)))
    # Cross past the horizon — terminal chunk fires.
    terminal_intents = strat.on_event(_state(t0 + timedelta(seconds=11.0)))
    assert any(i.tag == "ow_terminal" for i in terminal_intents)


def test_short_direction_yields_sell_orders() -> None:
    strat = ObizhaevaWangExecution(
        total_shares=-5.0, horizon_seconds=5.0, resilience=1.0, impact_coeff=1.0
    )
    intents = strat.on_event(_state(datetime(2024, 1, 1)))
    assert intents[0].side == "sell"


def test_continuous_phase_chunks_track_rate() -> None:
    strat = ObizhaevaWangExecution(
        total_shares=10.0,
        horizon_seconds=10.0,
        resilience=1.0,
        impact_coeff=1.0,
        tick_quantity=1.0,
    )
    t0 = datetime(2024, 1, 1)
    strat.on_event(_state(t0))
    # Continuous phase — emit at a few tick points and confirm we get
    # tagged ow_continuous orders without exceeding total_shares.
    cumulative = 0.0
    for s in range(1, 9):
        intents = strat.on_event(_state(t0 + timedelta(seconds=float(s))))
        for intent in intents:
            if intent.tag == "ow_continuous":
                cumulative += intent.quantity
    assert 0 < cumulative <= 10.0
