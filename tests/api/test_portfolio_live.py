"""Tests for the live portfolio monitoring service."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from aqp.persistence.models import Fill


@pytest.fixture
def seed_fills(in_memory_db) -> None:
    """Seed two fills (one buy, one sell) for AAA.NYSE so positions can compute."""
    from aqp.services import portfolio_service

    now = datetime.utcnow() - timedelta(days=2)
    with portfolio_service.get_session() as session:
        session.add(
            Fill(
                vt_symbol="AAA.NYSE",
                side="buy",
                quantity=100.0,
                price=10.0,
                commission=0.5,
                slippage=0.1,
                created_at=now,
            )
        )
        session.add(
            Fill(
                vt_symbol="AAA.NYSE",
                side="sell",
                quantity=20.0,
                price=11.0,
                commission=0.2,
                slippage=0.05,
                created_at=now + timedelta(hours=1),
            )
        )
        session.add(
            Fill(
                vt_symbol="BBB.NYSE",
                side="buy",
                quantity=50.0,
                price=20.0,
                commission=0.3,
                slippage=0.05,
                created_at=now,
            )
        )


def test_compute_positions_aggregates_signed_qty(seed_fills: None) -> None:
    from aqp.services.portfolio_service import compute_positions

    payload = compute_positions()
    by_sym = {p["vt_symbol"]: p for p in payload["positions"]}
    aaa = by_sym.get("AAA.NYSE")
    bbb = by_sym.get("BBB.NYSE")
    assert aaa is not None
    assert aaa["qty"] == pytest.approx(80.0)
    assert bbb is not None
    assert bbb["qty"] == pytest.approx(50.0)


def test_compute_exposures_split_long_short(seed_fills: None) -> None:
    from aqp.services.portfolio_service import compute_exposures

    payload = compute_exposures()
    assert "long_exposure" in payload
    assert "gross_exposure" in payload


def test_compute_pnl_series_returns_index(seed_fills: None) -> None:
    from aqp.services.portfolio_service import compute_pnl_series

    payload = compute_pnl_series(initial_cash=10_000.0)
    assert "index" in payload
    assert "equity" in payload
    assert len(payload["index"]) == len(payload["equity"])


def test_compute_allocations_groups(seed_fills: None) -> None:
    from aqp.services.portfolio_service import compute_allocations

    payload = compute_allocations(by="asset_class")
    assert payload["by"] == "asset_class"
    assert isinstance(payload["buckets"], list)


def test_compute_risk_returns_metrics(seed_fills: None) -> None:
    from aqp.services.portfolio_service import compute_risk

    payload = compute_risk(initial_cash=10_000.0)
    for key in ("sharpe", "max_drawdown", "var_95", "cvar_95", "ann_vol", "ann_return"):
        assert key in payload
