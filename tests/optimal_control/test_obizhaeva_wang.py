"""Tests for :mod:`aqp.optimal_control.obizhaeva_wang`."""
from __future__ import annotations

import numpy as np
import pytest

from aqp.optimal_control.obizhaeva_wang import (
    ObizhaevaWangParams,
    cost_vs_resilience,
    solve,
)


def test_closed_form_split_matches_paper_formula() -> None:
    """X0 = XT = X / (2 + rho*T) and Xc = rho*T*X / (2 + rho*T)."""
    p = ObizhaevaWangParams(
        total_shares=10.0,
        horizon=2.0,
        resilience=0.5,
        impact_coeff=1.0,
        grid_points=8,
    )
    res = solve(p)
    expected_chunk = 10.0 / (2.0 + 0.5 * 2.0)
    expected_cont = 0.5 * 2.0 * 10.0 / (2.0 + 0.5 * 2.0)
    assert res.initial_chunk == pytest.approx(expected_chunk, rel=1e-6)
    assert res.terminal_chunk == pytest.approx(expected_chunk, rel=1e-6)
    assert res.continuous_total == pytest.approx(expected_cont, rel=1e-6)


def test_cumulative_trajectory_monotonic_and_terminates_at_X() -> None:
    p = ObizhaevaWangParams(
        total_shares=100.0,
        horizon=4.0,
        resilience=2.0,
        impact_coeff=0.5,
        grid_points=32,
    )
    res = solve(p)
    assert res.cumulative_executed[0] == pytest.approx(res.initial_chunk)
    assert res.cumulative_executed[-1] == pytest.approx(100.0, rel=1e-6)
    diffs = np.diff(res.cumulative_executed)
    assert np.all(diffs >= -1e-9)


def test_cost_decreases_in_resilience() -> None:
    """A more resilient book makes patience cheaper."""
    p = ObizhaevaWangParams(total_shares=10.0, horizon=1.0, impact_coeff=1.0)
    sweep = cost_vs_resilience(p, rho_grid=np.array([0.1, 1.0, 10.0]))
    costs = sweep["expected_cost"]
    assert costs[0] > costs[1] > costs[2]


def test_zero_resilience_falls_back_to_naive_split() -> None:
    """With rho=0 the optimal trade is X/2 at t=0 and X/2 at t=T."""
    p = ObizhaevaWangParams(
        total_shares=20.0, horizon=1.0, resilience=1e-9, impact_coeff=1.0
    )
    res = solve(p)
    assert res.initial_chunk == pytest.approx(10.0, rel=1e-5)
    assert res.terminal_chunk == pytest.approx(10.0, rel=1e-5)
    assert res.continuous_total == pytest.approx(0.0, abs=1e-5)


def test_registry_entry_for_strategy() -> None:
    from aqp.core.registry import resolve

    cls = resolve("ObizhaevaWangExecution")
    from aqp.strategies.hft.obizhaeva_wang_exec import ObizhaevaWangExecution

    assert cls is ObizhaevaWangExecution
