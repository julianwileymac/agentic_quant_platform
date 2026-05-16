"""Sanity checks for :mod:`aqp.options.portfolio_mm`.

The closed-form Lucic-Tse Riccati solver collapses to a few invariants
we can verify analytically without sweeping a large parameter space:

1. With ``realized_vol == implied_vol`` the per-strike vol-arb PnL is zero.
2. With zero inventory the inventory-skew term is zero.
3. Bid/ask matrices respect ``bid <= mid <= ask`` for non-toxic configs.
"""
from __future__ import annotations

import numpy as np

from aqp.options.portfolio_mm import (
    LucicTseParams,
    compute_lucic_tse_quotes,
    expected_vol_arb_pnl,
)


def _toy_chain():
    expiries = np.array([0.05, 0.1, 0.25])
    strikes = np.array([95.0, 100.0, 105.0])
    n_e, n_k = len(expiries), len(strikes)
    spot = 100.0
    rate = 0.0
    vol = 0.20
    # Pre-computed BSM grid via the existing pricer.
    from aqp.analysis.pricing import greeks_grid

    grid = greeks_grid(
        spot=spot,
        strikes=strikes,
        expiries=expiries,
        rate=rate,
        vol=vol,
        option_type="call",
    )
    inventory = np.zeros((n_e, n_k))
    return spot, grid, inventory


def test_zero_vol_gap_implies_zero_pnl() -> None:
    spot, grid, inventory = _toy_chain()
    pnl = expected_vol_arb_pnl(
        spot=spot,
        gamma_surface=grid["gamma"],
        realized_vol=0.20,
        implied_vol=np.full_like(grid["gamma"], 0.20),
    )
    assert np.allclose(pnl, 0.0, atol=1e-12)


def test_positive_vol_gap_yields_positive_pnl() -> None:
    spot, grid, inventory = _toy_chain()
    pnl = expected_vol_arb_pnl(
        spot=spot,
        gamma_surface=grid["gamma"],
        realized_vol=0.25,
        implied_vol=np.full_like(grid["gamma"], 0.20),
    )
    # Higher realised vol than implied => agent sells gamma => positive PnL.
    assert (pnl > 0.0).all()


def test_zero_inventory_zero_skew() -> None:
    spot, grid, inventory = _toy_chain()
    quotes = compute_lucic_tse_quotes(
        spot=spot,
        mid_quotes=grid["price"],
        gamma_surface=grid["gamma"],
        vega_surface=grid["vega"],
        realized_vol=0.20,
        implied_vol=np.full_like(grid["price"], 0.20),
        inventory=inventory,
        params=LucicTseParams(gamma_inv=0.05, base_spread=0.05, hedge_cost=0.0),
    )
    assert np.allclose(quotes.inventory_skew, 0.0, atol=1e-12)


def test_bid_below_mid_ask_above_mid_when_inventory_zero() -> None:
    spot, grid, inventory = _toy_chain()
    quotes = compute_lucic_tse_quotes(
        spot=spot,
        mid_quotes=grid["price"],
        gamma_surface=grid["gamma"],
        vega_surface=grid["vega"],
        realized_vol=0.20,
        implied_vol=np.full_like(grid["price"], 0.20),
        inventory=inventory,
        params=LucicTseParams(gamma_inv=0.05, base_spread=0.05, hedge_cost=0.0),
    )
    assert (quotes.bid <= grid["price"]).all()
    assert (quotes.ask >= grid["price"]).all()


def test_summary_dict_shape() -> None:
    spot, grid, inventory = _toy_chain()
    quotes = compute_lucic_tse_quotes(
        spot=spot,
        mid_quotes=grid["price"],
        gamma_surface=grid["gamma"],
        vega_surface=grid["vega"],
        realized_vol=0.22,
        implied_vol=np.full_like(grid["price"], 0.20),
        inventory=inventory,
    )
    summary = quotes.to_summary()
    assert summary["n_expiries"] == grid["price"].shape[0]
    assert summary["n_strikes"] == grid["price"].shape[1]
    assert "total_expected_pnl" in summary
