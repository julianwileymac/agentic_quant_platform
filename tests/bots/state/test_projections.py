"""Phase 4: CQRS projections (position + PnL)."""
from __future__ import annotations

from decimal import Decimal

from aqp_bots.state.projections import PnLProjection, PositionProjection


def test_position_accumulates_volume_weighted() -> None:
    proj = PositionProjection()
    proj.apply_fill(venue="alpaca", symbol="AAPL", side="buy", qty=Decimal("50"), price=Decimal("100"))
    proj.apply_fill(venue="alpaca", symbol="AAPL", side="buy", qty=Decimal("50"), price=Decimal("110"))
    snap = proj.snapshot()
    aapl = snap["alpaca:AAPL"]
    # 100 long; VWAP = 105
    assert aapl["qty"] == "100"
    assert aapl["avg_price"] == "105"


def test_reducing_position_realizes_pnl() -> None:
    proj = PositionProjection()
    proj.apply_fill(venue="alpaca", symbol="AAPL", side="buy", qty=Decimal("100"), price=Decimal("100"))
    proj.apply_fill(venue="alpaca", symbol="AAPL", side="sell", qty=Decimal("50"), price=Decimal("110"))
    snap = proj.snapshot()
    aapl = snap["alpaca:AAPL"]
    # Sold 50 at 110, avg = 100; realized = 50 * (110 - 100) = 500.
    assert aapl["realized_pnl"] == "500"
    assert aapl["qty"] == "50"


def test_pnl_projection_aggregates() -> None:
    pos = PositionProjection()
    pos.apply_fill(venue="v", symbol="A", side="buy", qty=Decimal("10"), price=Decimal("100"))
    pos.apply_fill(venue="v", symbol="A", side="sell", qty=Decimal("5"), price=Decimal("120"))
    pnl = PnLProjection(position=pos)
    pnl.mark("v", "A", Decimal("130"))
    snap = pnl.snapshot()
    # Realized: 5 * (120 - 100) = 100
    # Unrealized: 5 * (130 - 100) = 150 (5 long at avg 100, mark 130)
    assert snap["realized"] == "100"
    assert snap["unrealized"] == "150"
    assert snap["total"] == "250"
