"""Cross-check the JAX Greeks fast path against the SciPy slow path.

The JAX backend isn't always available in CI (the ``optimal-control``
extra is opt-in). When it's not, ``greeks_grid_jax`` returns ``None``
and ``greeks_grid`` falls back to the SciPy double-loop. We test both
paths produce numerically equivalent surfaces.
"""
from __future__ import annotations

import numpy as np
import pytest

from aqp.analysis.pricing import greeks_grid


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_jax_path_matches_scipy_path_when_available(option_type: str) -> None:
    strikes = np.array([95.0, 100.0, 105.0])
    expiries = np.array([0.05, 0.1, 0.25])

    scipy_grid = greeks_grid(
        spot=100.0,
        strikes=strikes,
        expiries=expiries,
        rate=0.01,
        vol=0.2,
        option_type=option_type,
        use_jax=False,
    )
    jax_grid = greeks_grid(
        spot=100.0,
        strikes=strikes,
        expiries=expiries,
        rate=0.01,
        vol=0.2,
        option_type=option_type,
        use_jax=True,
    )

    # Even when JAX isn't installed the wrapper returns the SciPy result
    # for use_jax=True. Either way the two grids should be numerically
    # equivalent within a generous tolerance.
    for key in ("price", "delta", "gamma", "vega", "theta", "rho"):
        assert np.allclose(
            scipy_grid[key], jax_grid[key], atol=1e-4, rtol=1e-4
        ), f"{key} differs between scipy and jax paths"


def test_grid_shapes() -> None:
    strikes = np.linspace(90.0, 110.0, 7)
    expiries = np.linspace(0.05, 0.5, 4)
    grid = greeks_grid(
        spot=100.0,
        strikes=strikes,
        expiries=expiries,
        rate=0.0,
        vol=0.2,
    )
    for key in ("price", "delta", "gamma", "vega", "theta", "rho"):
        assert grid[key].shape == (len(expiries), len(strikes))
