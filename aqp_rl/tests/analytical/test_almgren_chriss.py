"""Almgren-Chriss 2001 closed-form acceptance tests.

Locks in the worked example from §2 of Almgren & Chriss 2001
("Optimal execution of portfolio transactions") — the canonical
sanity-check numbers practitioners use to validate any AC
implementation::

    γ = 2.5e-7, η = 2.5e-6, ε = 0.0625, σ = 0.95, λ = 1e-6, X = 1e6, T = 5d

For these inputs the paper reports ``κ ≈ 0.6 / day``. Our default
:class:`AlmgrenChrissParams` uses these exact values so a bare
``AlmgrenChrissParams()`` reproduces the paper's number.

Additionally checks:

1. ``sum(trade_list) == total_shares`` to 1e-6 tolerance.
2. ``positions[0] == X`` and ``positions[-1] == 0``.
3. Per-step positions monotonically decay (for the liquidation case).
4. ``cost_expectation`` and ``cost_variance`` are non-negative.
5. ``cost_variance`` increases monotonically with ``risk_aversion``
   when ``risk_aversion → 0`` (a risk-neutral trader liquidates more
   slowly ⇒ holds more inventory ⇒ higher variance).
6. Round-trip ``AlmgrenChrissSchedule`` recomputes consistently.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from aqp_rl.analytical.almgren_chriss import (
    AlmgrenChrissParams,
    AlmgrenChrissSchedule,
    build_schedule,
    cost_expectation,
    cost_variance,
    kappa,
    optimal_positions,
    trade_list,
)


def test_kappa_matches_paper_worked_example():
    """κ ≈ 0.6 / day for the paper's published parameter set."""
    params = AlmgrenChrissParams()  # defaults match the paper
    κ = kappa(params)
    assert κ == pytest.approx(0.6164, abs=5e-3)


def test_trade_list_sums_to_total_shares():
    params = AlmgrenChrissParams()
    n = trade_list(params)
    assert n.shape == (params.num_trades,)
    assert float(np.sum(n)) == pytest.approx(params.total_shares, rel=1e-9)


def test_positions_start_at_X_end_at_zero():
    params = AlmgrenChrissParams()
    x = optimal_positions(params)
    assert x.shape == (params.num_trades + 1,)
    assert x[0] == pytest.approx(params.total_shares, rel=1e-9)
    assert x[-1] == pytest.approx(0.0, abs=1e-9)


def test_positions_monotone_decay_for_liquidation():
    params = AlmgrenChrissParams()
    x = optimal_positions(params)
    diffs = np.diff(x)
    assert (diffs <= 0).all()


def test_cost_expectation_nonneg():
    params = AlmgrenChrissParams()
    e = cost_expectation(params)
    assert e >= 0


def test_cost_variance_nonneg():
    params = AlmgrenChrissParams()
    v = cost_variance(params)
    assert v >= 0


def test_low_risk_aversion_yields_more_variance_than_high():
    """λ↓ ⇒ trader is risk-neutral ⇒ slower liquidation ⇒ higher variance."""
    p_low_lambda = AlmgrenChrissParams(risk_aversion=1e-8)
    p_high_lambda = AlmgrenChrissParams(risk_aversion=1e-4)
    v_low = cost_variance(p_low_lambda)
    v_high = cost_variance(p_high_lambda)
    assert v_low > v_high


def test_high_risk_aversion_yields_aggressive_front_loading():
    """λ↑ ⇒ trader front-loads ⇒ first trade > last trade."""
    params = AlmgrenChrissParams(risk_aversion=1e-2)  # very risk averse
    n = trade_list(params)
    assert n[0] > n[-1]


def test_build_schedule_consistency():
    params = AlmgrenChrissParams()
    sched = build_schedule(params)
    assert isinstance(sched, AlmgrenChrissSchedule)
    assert sched.kappa == pytest.approx(kappa(params))
    np.testing.assert_allclose(sched.trades, trade_list(params))
    np.testing.assert_allclose(sched.positions, optimal_positions(params))
    assert sched.expected_cost == pytest.approx(cost_expectation(params))
    assert sched.cost_variance == pytest.approx(cost_variance(params))


def test_invalid_num_trades_raises():
    with pytest.raises(ValueError):
        AlmgrenChrissParams(num_trades=0).tau  # noqa: B018


def test_invalid_eta_relative_to_gamma_raises():
    """When γ·τ/2 ≥ η the model is undefined."""
    p = AlmgrenChrissParams(eta=1e-9, gamma=1.0, num_trades=10)
    with pytest.raises(ValueError):
        _ = p.eta_tilde


def test_kappa_increases_with_risk_aversion():
    """κ² = λσ²/η̃ ⇒ κ scales with sqrt(λ) (other things equal)."""
    p1 = AlmgrenChrissParams(risk_aversion=1e-6)
    p2 = AlmgrenChrissParams(risk_aversion=4e-6)
    κ1 = kappa(p1)
    κ2 = kappa(p2)
    # Doubling risk aversion ⇒ κ scales by sqrt(2) → halve / quadrupling ⇒ 2×
    assert κ2 == pytest.approx(2.0 * κ1, rel=1e-9)


def test_extreme_low_risk_yields_near_linear_schedule():
    """λ → 0 ⇒ uniform (linear) schedule ⇒ all n_k approximately equal."""
    params = AlmgrenChrissParams(risk_aversion=1e-15, num_trades=10)
    n = trade_list(params)
    mean_trade = float(np.mean(n))
    # Each trade within 5% of the mean.
    for trade in n:
        assert abs(trade - mean_trade) / mean_trade < 0.05


def test_paper_example_holds_at_default_kappa_tau():
    """``κ · τ ≈ 0.6164 · 1 = 0.6164`` for the default 5-day, 5-trade example."""
    params = AlmgrenChrissParams()
    κ = kappa(params)
    τ = params.tau
    assert τ == pytest.approx(1.0)  # 5 days / 5 trades
    assert κ * τ == pytest.approx(0.6164, abs=5e-3)
    # And cosh(κ·τ) checks out with cosh(0.6164) ≈ 1.196
    assert math.cosh(κ * τ) == pytest.approx(1.196, abs=1e-3)
