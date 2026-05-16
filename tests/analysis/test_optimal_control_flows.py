"""Smoke tests for the optimal-control analysis flows.

Verifies the four new flows under
``aqp.analysis.flows.optimal_control`` are registered, take the
expected params, and emit the expected metrics + rows shapes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from aqp.analysis import run_flow


def test_avst_flow_registered_and_runs() -> None:
    out = run_flow(
        "optimal_control.avellaneda_stoikov_quotes",
        None,
        {
            "mid_price": 100.0,
            "inventory_min": -10.0,
            "inventory_max": 10.0,
            "inventory_step": 5.0,
            "gamma": 0.1,
            "sigma": 0.01,
            "k": 1.5,
            "T_minus_t": 1.0,
        },
    )
    assert out.error is None
    assert "n_points" in out.metrics
    assert out.metrics["n_points"] == 5  # -10, -5, 0, 5, 10
    assert len(out.rows) == 5
    # All rows should have the canonical shape.
    for r in out.rows:
        assert {"inventory", "reservation_price", "half_spread", "bid", "ask"}.issubset(r)


def test_cj_flow_returns_value_function() -> None:
    out = run_flow(
        "optimal_control.cartea_jaimungal_liquidation",
        None,
        {
            "horizon": 0.5,
            "initial_inventory": 50.0,
            "sigma": 0.02,
            "phi": 1e-4,
            "alpha": 1e-3,
            "kappa": 1.0,
            "n_steps": 50,
        },
    )
    assert out.error is None
    assert "expected_pnl" in out.metrics
    # 50 + 1 grid points but rows are capped at 500 — equal here.
    assert len(out.rows) == 51
    for key in ("h0", "h1", "h2"):
        assert all(key in r for r in out.rows)


def test_lucic_tse_flow_returns_quote_matrix() -> None:
    out = run_flow(
        "optimal_control.lucic_tse_portfolio_quotes",
        None,
        {
            "spot": 100.0,
            "strikes": [95.0, 100.0, 105.0],
            "expiries": [0.05, 0.1, 0.25],
            "rate": 0.0,
            "realized_vol": 0.22,
            "implied_vol": 0.20,
            "inventory_per_strike": 0.0,
            "gamma_inv": 0.05,
            "base_spread": 0.05,
            "hedge_cost": 0.001,
            "option_type": "call",
        },
    )
    assert out.error is None
    assert out.metrics["n_strikes"] == 3
    assert out.metrics["n_expiries"] == 3
    assert len(out.rows) == 9  # 3 expiries x 3 strikes
    for r in out.rows:
        assert {"strike", "expiry", "bid", "ask", "mid", "half_spread"}.issubset(r)


def test_toxicity_regime_flow_classifies_benign() -> None:
    # Build a synthetic quiet-flow dataset — should classify as benign.
    n = 200
    df = pd.DataFrame(
        {
            "buy_volume": np.full(n, 100.0),
            "sell_volume": np.full(n, 100.0),
            "bid_qty": np.full(n, 50.0),
            "ask_qty": np.full(n, 50.0),
            "bid_price": np.full(n, 99.5),
            "ask_price": np.full(n, 100.5),
        }
    )
    out = run_flow(
        "optimal_control.toxicity_regime",
        df,
        {
            "buy_volume_column": "buy_volume",
            "sell_volume_column": "sell_volume",
            "bid_qty_column": "bid_qty",
            "ask_qty_column": "ask_qty",
            "bid_price_column": "bid_price",
            "ask_price_column": "ask_price",
            "n_buckets": 10,
            "toxic_threshold": 0.6,
        },
    )
    assert out.error is None
    assert out.metrics["regime"] == "benign"
    assert out.metrics["gamma_multiplier"] == 1.0
    assert out.metrics["order_size_multiplier"] == 1.0
