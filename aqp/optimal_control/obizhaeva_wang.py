"""Obizhaeva-Wang (2013) dynamic optimal execution.

Reference: Obizhaeva, A. A. & Wang, J. (2013). "Optimal trading
strategy and supply/demand dynamics." *Journal of Financial Markets*,
16(1), 1-32. (MIT working-paper 2005 precedes the published version.)

The model
=========

A trader must liquidate ``X`` shares over horizon ``T`` against a
linear-cost order book with finite resilience. The deviation of the
limit order book from its steady state, :math:`d_t`, follows

.. math::

    \\frac{dd_t}{dt} = -\\rho d_t + \\lambda \\dot v_t,

where :math:`\\dot v_t` is the trade flow, :math:`\\lambda` the linear
price-impact coefficient, and :math:`\\rho` the **resilience rate**
(speed at which the book replenishes after a market order). Optimal
strategy under linear costs is the celebrated discrete-continuous-
discrete profile:

1. **Initial discrete chunk** :math:`X_0` at :math:`t = 0` that pushes
   the book away from steady state.
2. **Continuous flow** :math:`\\dot v_t = \\rho X_c / (1 + \\rho T)` for
   :math:`t \\in (0, T)` that exactly matches the inflow of replenishing
   liquidity.
3. **Terminal discrete chunk** :math:`X_T` at :math:`t = T` that
   clears the remainder.

Closed form
===========

With cost coefficient :math:`\\lambda > 0`, resilience :math:`\\rho > 0`,
and horizon :math:`T`, the optimal split is

.. math::

    X_0 = X_T = \\frac{X}{2 + \\rho T}, \\quad
    X_c = \\frac{\\rho T \\cdot X}{2 + \\rho T}.

The expected execution cost (under the linear-impact assumption) is

.. math::

    C^* = \\lambda X^2 \\cdot \\frac{1}{2(2 + \\rho T)},

which monotonically decreases in :math:`\\rho T` — i.e. patience helps
exactly when the book replenishes fast enough.

JAX-compiled execution
======================

The compute kernels are pure JAX (with a NumPy fallback when JAX isn't
installed). Functions are JIT-friendly because they only contain
elementwise ops, no Python control flow on the values.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

# Reuse the same JAX import shim semantics as avellaneda_stoikov.
try:
    import jax  # type: ignore[import-not-found]
    import jax.numpy as jnp  # type: ignore[import-not-found]

    _JAX_AVAILABLE = True
except Exception:  # noqa: BLE001
    jax = None  # type: ignore[assignment]
    jnp = np  # type: ignore[assignment]
    _JAX_AVAILABLE = False


logger = logging.getLogger(__name__)


def _jit_or_passthrough(fn: Any) -> Any:
    if _JAX_AVAILABLE:
        return jax.jit(fn)  # type: ignore[union-attr]
    return fn


@dataclass(slots=True, frozen=True)
class ObizhaevaWangParams:
    """Knobs for a single OW liquidation solve.

    Defaults are tuned for an illustrative slice (e.g. liquidating
    1,000 shares over a 1-hour interval); real calibration uses
    ``lambda`` from a slope regression of price impact on trade size
    and ``rho`` from a half-life fit of book restitution.
    """

    total_shares: float = 1.0
    """Total signed quantity to liquidate (``X``)."""

    horizon: float = 1.0
    """Time horizon :math:`T` in the same units as ``resilience``."""

    resilience: float = 1.0
    """Book resilience :math:`\\rho`. Larger = faster replenishment."""

    impact_coeff: float = 1.0
    """Linear-impact coefficient :math:`\\lambda`."""

    grid_points: int = 64
    """Number of intermediate continuous-trade grid points (>= 2)."""


@dataclass(slots=True, frozen=True)
class ObizhaevaWangResult:
    """Solver output."""

    initial_chunk: float
    """Discrete trade size at :math:`t = 0`."""

    terminal_chunk: float
    """Discrete trade size at :math:`t = T`."""

    continuous_total: float
    """Total continuous-flow quantity between 0 and T."""

    continuous_rate: float
    """Constant continuous-trade rate :math:`\\dot v`."""

    times: np.ndarray
    """Time grid (length ``grid_points``) including endpoints."""

    cumulative_executed: np.ndarray
    """Cumulative executed quantity along the time grid."""

    expected_cost: float
    """Closed-form expected execution cost :math:`C^*`."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_chunk": float(self.initial_chunk),
            "terminal_chunk": float(self.terminal_chunk),
            "continuous_total": float(self.continuous_total),
            "continuous_rate": float(self.continuous_rate),
            "times": self.times.tolist(),
            "cumulative_executed": self.cumulative_executed.tolist(),
            "expected_cost": float(self.expected_cost),
        }


def _ow_kernel(
    total: Any,
    horizon: Any,
    resilience: Any,
    impact_coeff: Any,
) -> tuple[Any, Any, Any, Any]:
    """Pure compute: returns (X0, XT, Xc_rate, expected_cost).

    Encodes the closed-form OW solution. Pure-elementwise ops so the
    function JIT-compiles cleanly with JAX.
    """
    denom = 2.0 + resilience * horizon
    safe_denom = jnp.maximum(denom, 1e-12)
    chunk = total / safe_denom
    continuous = (resilience * horizon * total) / safe_denom
    rate = continuous / jnp.maximum(horizon, 1e-12)
    expected_cost = impact_coeff * total * total / (2.0 * safe_denom)
    return chunk, chunk, rate, expected_cost


_ow_kernel_jit = _jit_or_passthrough(_ow_kernel)


def solve(params: ObizhaevaWangParams | None = None, **overrides: Any) -> ObizhaevaWangResult:
    """Solve the OW liquidation problem and return the trade trajectory.

    Either pass a fully-formed :class:`ObizhaevaWangParams` or override
    individual knobs as keyword arguments.
    """
    p = params or ObizhaevaWangParams()
    total = float(overrides.get("total_shares", p.total_shares))
    horizon = float(overrides.get("horizon", p.horizon))
    resilience = float(overrides.get("resilience", p.resilience))
    impact = float(overrides.get("impact_coeff", p.impact_coeff))
    grid = int(overrides.get("grid_points", p.grid_points))
    if grid < 2:
        grid = 2

    x0, xT, rate, cost = _ow_kernel_jit(total, horizon, resilience, impact)
    x0_f = float(x0)
    xT_f = float(xT)
    rate_f = float(rate)
    cost_f = float(cost)
    continuous_total = max(total - x0_f - xT_f, 0.0)

    times = np.linspace(0.0, horizon, grid)
    cum = np.where(
        times <= 0.0,
        x0_f,
        x0_f + rate_f * times,
    )
    # Add the terminal lump at t == T.
    cum[-1] = total
    return ObizhaevaWangResult(
        initial_chunk=x0_f,
        terminal_chunk=xT_f,
        continuous_total=continuous_total,
        continuous_rate=rate_f,
        times=times,
        cumulative_executed=cum,
        expected_cost=cost_f,
    )


def cost_vs_resilience(
    params: ObizhaevaWangParams,
    *,
    rho_grid: np.ndarray,
) -> dict[str, np.ndarray]:
    """Sensitivity sweep: expected cost as a function of resilience.

    Useful for the ``analysis.optimal_control.obizhaeva_wang_solve``
    flow: pass a grid of candidate :math:`\\rho` values and inspect
    cost. Powered by ``vmap`` when JAX is installed; falls back to a
    Python loop otherwise.
    """
    rhos = np.asarray(rho_grid, dtype=float)
    if _JAX_AVAILABLE:
        kernel = jax.jit(
            lambda rho: _ow_kernel(
                params.total_shares,
                params.horizon,
                rho,
                params.impact_coeff,
            )[3]
        )
        costs = np.asarray(jax.vmap(kernel)(jnp.asarray(rhos)))
    else:
        costs = np.array(
            [
                _ow_kernel(
                    params.total_shares,
                    params.horizon,
                    float(rho),
                    params.impact_coeff,
                )[3]
                for rho in rhos
            ],
            dtype=float,
        )
    return {"rho": rhos, "expected_cost": costs}
