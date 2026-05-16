"""Sanity checks for the Cartea-Jaimungal RK4 solver.

Non-JAX path is the default since the module ships a pure-NumPy
fallback; tests here verify the linear-quadratic ansatz behaves
correctly:

1. Terminal conditions: ``h_2(T) = -alpha``, ``h_1(T) = h_0(T) = 0``.
2. With ``phi = 0`` and ``alpha = 0`` the solution is identically zero
   (no inventory cost anywhere => optimal rate is zero).
3. Trading rate is positive when inventory is positive (we sell to
   liquidate).
"""
from __future__ import annotations

import math

import numpy as np

from aqp.optimal_control.cartea_jaimungal import (
    CarteaJaimungalParams,
    optimal_trading_rate,
    solve,
)
from aqp.optimal_control.hjb_solver import solve_cj


def test_terminal_conditions() -> None:
    result = solve(
        CarteaJaimungalParams(
            horizon=1.0,
            initial_inventory=100.0,
            sigma=0.01,
            phi=1e-4,
            alpha=1e-3,
            kappa=1.0,
            n_steps=100,
        )
    )
    # Terminal point of the t-grid is index 0 (we reverse so t-grid is
    # increasing). At ``t=T`` we have h2 = -alpha.
    # The solver returns t_grid running forwards in time => last entry is T.
    assert math.isclose(result.h2[-1], -1e-3, rel_tol=1e-6, abs_tol=1e-9)
    assert math.isclose(result.h1[-1], 0.0, abs_tol=1e-9)
    assert math.isclose(result.h0[-1], 0.0, abs_tol=1e-9)


def test_zero_penalties_zero_solution() -> None:
    result = solve(
        CarteaJaimungalParams(
            horizon=1.0,
            initial_inventory=100.0,
            sigma=0.01,
            phi=0.0,
            alpha=0.0,
            kappa=1.0,
            n_steps=50,
        )
    )
    assert np.allclose(result.h2, 0.0, atol=1e-9)
    assert np.allclose(result.h1, 0.0, atol=1e-9)
    assert np.allclose(result.h0, 0.0, atol=1e-9)


def test_optimal_rate_sign_matches_inventory() -> None:
    # phi > 0 => h2 < 0 => optimal_trading_rate > 0 for positive inventory.
    rate_long = optimal_trading_rate(
        inventory=100.0, h2=-0.01, h1=0.0, kappa=1.0
    )
    rate_short = optimal_trading_rate(
        inventory=-100.0, h2=-0.01, h1=0.0, kappa=1.0
    )
    assert rate_long > 0  # selling
    assert rate_short < 0  # buying back


def test_solve_cj_helper_returns_dict() -> None:
    out = solve_cj(
        horizon=0.5,
        initial_inventory=50.0,
        sigma=0.02,
        phi=1e-4,
        alpha=1e-3,
        kappa=1.0,
        n_steps=20,
    )
    assert "metrics" in out and "rows" in out
    assert out["metrics"]["n_steps"] == 21  # n_steps + 1 for grid points
    assert len(out["rows"]) == 21
    assert all({"t", "h2", "h1", "h0", "inventory", "cash"}.issubset(r) for r in out["rows"])
