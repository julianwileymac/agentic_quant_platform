"""Derivatives flows + pricing primitives — math-only smoke tests."""
from __future__ import annotations

import math

import pytest

from aqp.analysis import pricing, run_flow


def test_bsm_call_matches_textbook() -> None:
    """At spot=100, strike=100, vol=20%, ttm=1y, r=5% the BSM call price
    is ~10.4506 (well-known textbook reference)."""
    res = pricing.bsm_price(
        spot=100, strike=100, rate=0.05, vol=0.2, ttm=1.0, option_type="call"
    )
    assert math.isclose(res.price, 10.4506, abs_tol=1e-2)
    assert res.delta > 0
    assert res.gamma > 0
    assert res.vega > 0


def test_bsm_put_call_parity() -> None:
    spot, strike, rate, vol, ttm = 100, 100, 0.03, 0.25, 1.0
    call = pricing.bsm_price(
        spot=spot, strike=strike, rate=rate, vol=vol, ttm=ttm, option_type="call"
    ).price
    put = pricing.bsm_price(
        spot=spot, strike=strike, rate=rate, vol=vol, ttm=ttm, option_type="put"
    ).price
    pv_strike = strike * math.exp(-rate * ttm)
    # C - P = S - K * e^{-rT}
    assert math.isclose(call - put, spot - pv_strike, abs_tol=1e-4)


def test_bsm_flow_returns_greeks() -> None:
    out = run_flow(
        "derivatives.bsm",
        None,
        {
            "spot": 100,
            "strike": 105,
            "rate": 0.05,
            "vol": 0.2,
            "ttm": 0.5,
            "option_type": "call",
        },
    )
    assert "delta" in out.metrics
    assert "gamma" in out.metrics
    assert out.metrics["price"] > 0


def test_mc_european_within_two_se_of_bsm() -> None:
    out = run_flow(
        "derivatives.monte_carlo_european",
        None,
        {
            "spot": 100,
            "strike": 100,
            "rate": 0.05,
            "vol": 0.2,
            "ttm": 1.0,
            "n_paths": 50_000,
            "n_steps": 50,
            "option_type": "call",
            "seed": 42,
        },
    )
    bsm = out.metrics["bsm_reference"]
    mc = out.metrics["price"]
    se = out.metrics["std_error"]
    assert abs(mc - bsm) < 5 * se


def test_implied_vol_recovers_input() -> None:
    target_vol = 0.25
    market_price = pricing.bsm_price(
        spot=100, strike=100, rate=0.0, vol=target_vol, ttm=1.0, option_type="call"
    ).price
    out = run_flow(
        "derivatives.implied_volatility",
        None,
        {
            "market_price": market_price,
            "spot": 100,
            "strike": 100,
            "rate": 0.0,
            "ttm": 1.0,
            "option_type": "call",
        },
    )
    assert math.isclose(out.metrics["implied_vol"], target_vol, abs_tol=1e-3)


def test_greeks_surface_shape() -> None:
    out = run_flow(
        "derivatives.greeks_surface",
        None,
        {
            "spot": 100,
            "strikes": [90, 100, 110],
            "expiries": [0.25, 0.5, 1.0],
            "vol": 0.2,
            "rate": 0.05,
            "option_type": "call",
        },
    )
    assert len(out.rows) == 9  # 3 strikes x 3 expiries
    assert out.chart is not None
