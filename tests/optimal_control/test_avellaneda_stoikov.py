"""Analytical sanity checks for :mod:`aqp.optimal_control.avellaneda_stoikov`.

The kernels are pure math so we can test them without JAX installed —
the module degrades to NumPy fallbacks. The tests below check three
limits that fall directly out of the closed forms:

1. At zero inventory, the reservation price equals the mid.
2. Half-spread monotonically grows with ``gamma * sigma**2 * (T-t)``.
3. ``glft_closed_form`` and ``compute_optimal_quotes`` agree on the
   reservation price (they share the inventory-skew term).
"""
from __future__ import annotations

import math

from aqp.optimal_control.avellaneda_stoikov import (
    AvellanedaStoikovParams,
    compute_optimal_quotes,
    glft_closed_form,
    quote_grid,
)


def test_zero_inventory_reservation_equals_mid() -> None:
    res = compute_optimal_quotes(
        mid_price=100.0,
        inventory=0.0,
        gamma=0.1,
        sigma=0.02,
        k=1.5,
        T_minus_t=1.0,
    )
    assert math.isclose(res.reservation_price, 100.0, rel_tol=1e-9)


def test_inventory_skews_quotes() -> None:
    long_res = compute_optimal_quotes(
        mid_price=100.0,
        inventory=10.0,
        gamma=0.1,
        sigma=0.02,
        k=1.5,
        T_minus_t=1.0,
    )
    short_res = compute_optimal_quotes(
        mid_price=100.0,
        inventory=-10.0,
        gamma=0.1,
        sigma=0.02,
        k=1.5,
        T_minus_t=1.0,
    )
    # Long inventory => reservation < mid => more aggressive ask, less bid.
    assert long_res.reservation_price < 100.0 < short_res.reservation_price
    assert long_res.bid < short_res.bid
    assert long_res.ask < short_res.ask


def test_half_spread_grows_with_sigma_and_horizon() -> None:
    """
    The Avellaneda-Stoikov half-spread is

        delta = 0.5 * gamma * sigma**2 * (T - t) + (1/gamma) * ln(1 + gamma/k)

    The first term is monotone in sigma**2 * (T - t); the second is
    monotone-decreasing in gamma (the 1/gamma scaling dominates ln
    growth). So we only assert the unambiguous monotonicities here.
    """
    base = compute_optimal_quotes(
        mid_price=100.0, inventory=0.0,
        gamma=0.1, sigma=0.01, k=1.5, T_minus_t=1.0,
    )
    bigger_sigma = compute_optimal_quotes(
        mid_price=100.0, inventory=0.0,
        gamma=0.1, sigma=0.05, k=1.5, T_minus_t=1.0,
    )
    longer_horizon = compute_optimal_quotes(
        mid_price=100.0, inventory=0.0,
        gamma=0.1, sigma=0.01, k=1.5, T_minus_t=5.0,
    )
    # Bigger sigma and longer horizon strictly widen the spread.
    assert bigger_sigma.half_spread > base.half_spread
    assert longer_horizon.half_spread > base.half_spread


def test_half_spread_skews_with_gamma_at_nonzero_inventory() -> None:
    """At non-zero inventory, larger gamma yields a stronger reservation
    skew (``-q · gamma · sigma**2 · (T-t)``)."""
    smaller_gamma = compute_optimal_quotes(
        mid_price=100.0, inventory=10.0,
        gamma=0.05, sigma=0.05, k=1.5, T_minus_t=1.0,
    )
    bigger_gamma = compute_optimal_quotes(
        mid_price=100.0, inventory=10.0,
        gamma=0.5, sigma=0.05, k=1.5, T_minus_t=1.0,
    )
    # Reservation price is shifted further below mid as gamma grows.
    assert bigger_gamma.reservation_price < smaller_gamma.reservation_price
    assert bigger_gamma.reservation_price < 100.0


def test_glft_and_avst_share_reservation_term() -> None:
    res_avst = compute_optimal_quotes(
        mid_price=50.0, inventory=5.0,
        gamma=0.1, sigma=0.02, k=1.5, T_minus_t=1.0,
    )
    res_glft = glft_closed_form(
        mid_price=50.0, inventory=5.0, gamma=0.1, sigma=0.02, kappa=1.5,
    )
    # Both share the inventory-skew term -q*gamma*sigma^2 — equal here.
    assert math.isclose(
        res_avst.reservation_price, res_glft.reservation_price, abs_tol=1e-6
    )


def test_quote_grid_returns_arrays() -> None:
    import numpy as np

    grid = np.arange(-20, 21, 5, dtype=float)
    out = quote_grid(
        mid_price=100.0,
        inventory_grid=grid,
        params=AvellanedaStoikovParams(gamma=0.1, sigma=0.02, k=1.5, T_minus_t=1.0),
    )
    assert out["bid"].shape == grid.shape
    assert out["ask"].shape == grid.shape
    # Reservation at zero inventory equals mid.
    zero_idx = int(np.argmin(np.abs(grid)))
    assert math.isclose(out["reservation_price"][zero_idx], 100.0, rel_tol=1e-6)
