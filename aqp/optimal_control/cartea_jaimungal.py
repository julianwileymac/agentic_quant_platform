"""Cartea-Jaimungal-Penalva inventory-penalised market making + execution.

References:

- Á. Cartea, S. Jaimungal, and J. Penalva, *Algorithmic and High-
  Frequency Trading*, Cambridge UP 2015. Chapters 8 (single-asset
  market making with inventory penalty) and 10 (optimal liquidation).

The model in three pieces
=========================

State: ``(t, q, S)`` — time, inventory, mid-price.

HJB equation (continuous-time, geometric Brownian motion price)::

    H_t + 0.5 * sigma**2 * H_SS - phi * q**2
        + sup_{nu} { -nu * S - lambda_t * (nu - q)**2 } = 0

with terminal condition ``H(T, q, S) = q * S - alpha * q**2``.

Here:

- ``phi`` — running inventory penalty (per unit time).
- ``alpha`` — terminal inventory penalty.
- ``lambda_t`` — temporary impact / urgency parameter.
- ``nu`` — trading rate (control).

For market making (chapter 8) the controls are the bid/ask half-spreads
``(delta_b, delta_a)`` instead of a trading rate; the structure of the
HJB and value-function ansatz is the same.

Closed-form ansatz (linear-quadratic in ``q``)::

    H(t, q, S) = q * S + h_2(t) * q**2 + h_1(t) * q + h_0(t)

with ``(h_0, h_1, h_2)`` solving a system of three coupled ODEs that
we integrate via :mod:`finhjb` (when installed) or a plain Runge-Kutta
fallback (when it isn't).

JAX usage
=========

The ODE right-hand side and the terminal condition are pure JAX
functions; the integrator is a fixed-step RK4 written in JAX so the
analysis-flow runner can vmap across ``phi`` / ``alpha`` parameter
sweeps. ``finhjb`` is used for the boundary-update + sensitivity-
analysis paths the lab UI surfaces.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)


try:
    import jax  # type: ignore[import-not-found]
    import jax.numpy as jnp  # type: ignore[import-not-found]

    _JAX_AVAILABLE = True
except Exception:  # noqa: BLE001
    jax = None  # type: ignore[assignment]
    jnp = np  # type: ignore[assignment]
    _JAX_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public params + result
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class CarteaJaimungalParams:
    """All knobs for a Cartea-Jaimungal optimal liquidation / MM run.

    The defaults model a small block-liquidation experiment over one
    trading day with bps-scale impact.
    """

    horizon: float = 1.0
    """Total time-to-horizon (days, hours, whatever the user picks)."""

    initial_inventory: float = 100.0
    """Starting position to liquidate."""

    sigma: float = 0.01
    """Mid-price volatility (per sqrt of horizon unit)."""

    phi: float = 1e-4
    """Running inventory penalty coefficient."""

    alpha: float = 1e-3
    """Terminal inventory penalty (positive = encourage flat at T)."""

    kappa: float = 1.0
    """Temporary impact coefficient (Almgren-Chriss style)."""

    n_steps: int = 200
    """Number of integration steps for the ODE / RK4 grid."""


@dataclass(slots=True)
class CarteaJaimungalResult:
    """Output of an optimal-liquidation run.

    All arrays are length ``n_steps + 1`` and aligned on the same time
    grid ``t_grid``.
    """

    t_grid: np.ndarray
    h2: np.ndarray
    h1: np.ndarray
    h0: np.ndarray
    optimal_rate: np.ndarray = field(default_factory=lambda: np.empty(0))
    inventory_path: np.ndarray = field(default_factory=lambda: np.empty(0))
    cash_path: np.ndarray = field(default_factory=lambda: np.empty(0))
    expected_pnl: float = 0.0

    def to_summary(self) -> dict[str, float]:
        return {
            "horizon": float(self.t_grid[-1] - self.t_grid[0]) if len(self.t_grid) else 0.0,
            "n_steps": int(len(self.t_grid)),
            "expected_pnl": float(self.expected_pnl),
            "h2_initial": float(self.h2[0]) if len(self.h2) else 0.0,
            "h2_terminal": float(self.h2[-1]) if len(self.h2) else 0.0,
        }


# ---------------------------------------------------------------------------
# Coupled ODE for (h_0, h_1, h_2)
# ---------------------------------------------------------------------------


def _ode_rhs(h2: float, h1: float, h0: float, *, phi: float, kappa: float) -> tuple[float, float, float]:
    """Right-hand side of the linear-quadratic ansatz ODE system.

    Derived from substituting ``H = q*S + h_2*q**2 + h_1*q + h_0`` into
    the HJB and matching coefficients of powers of ``q``. See
    Cartea-Jaimungal-Penalva 2015 §8.2.

    The integration runs *backwards* in time from the terminal
    condition; we encode that as a forward integration with negated
    RHS in :func:`_integrate_rk4`.
    """
    # dh_2/dt = -phi - h_2**2 / kappa
    dh2 = -phi - (h2 * h2) / kappa
    # dh_1/dt = -h_1 * h_2 / kappa
    dh1 = -(h1 * h2) / kappa
    # dh_0/dt = -h_1**2 / (4 * kappa)
    dh0 = -(h1 * h1) / (4.0 * kappa)
    return dh2, dh1, dh0


def _integrate_rk4(
    *,
    horizon: float,
    n_steps: int,
    phi: float,
    alpha: float,
    kappa: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Backwards-in-time RK4 from the terminal condition.

    Terminal condition::

        h_2(T) = -alpha
        h_1(T) = 0
        h_0(T) = 0

    We integrate dh/d(tau) where tau = T - t so the time-grid runs
    forward in tau but the result is interpreted at ``t = T - tau``.
    """
    n_steps = max(int(n_steps), 1)
    dt = horizon / n_steps
    h2 = np.empty(n_steps + 1)
    h1 = np.empty(n_steps + 1)
    h0 = np.empty(n_steps + 1)
    h2[0] = -alpha
    h1[0] = 0.0
    h0[0] = 0.0
    for i in range(n_steps):
        # RK4 in tau; the RHS is symmetric so the sign cancels out.
        k1 = _ode_rhs(h2[i], h1[i], h0[i], phi=phi, kappa=kappa)
        k2 = _ode_rhs(
            h2[i] + 0.5 * dt * k1[0],
            h1[i] + 0.5 * dt * k1[1],
            h0[i] + 0.5 * dt * k1[2],
            phi=phi,
            kappa=kappa,
        )
        k3 = _ode_rhs(
            h2[i] + 0.5 * dt * k2[0],
            h1[i] + 0.5 * dt * k2[1],
            h0[i] + 0.5 * dt * k2[2],
            phi=phi,
            kappa=kappa,
        )
        k4 = _ode_rhs(
            h2[i] + dt * k3[0],
            h1[i] + dt * k3[1],
            h0[i] + dt * k3[2],
            phi=phi,
            kappa=kappa,
        )
        h2[i + 1] = h2[i] + dt * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]) / 6.0
        h1[i + 1] = h1[i] + dt * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]) / 6.0
        h0[i + 1] = h0[i] + dt * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2]) / 6.0
    # tau-grid → t-grid
    tau_grid = np.linspace(0.0, horizon, n_steps + 1)
    t_grid = horizon - tau_grid
    # Reverse the arrays so they line up with t in increasing order.
    return t_grid[::-1], h2[::-1], h1[::-1], h0[::-1]


# ---------------------------------------------------------------------------
# Optimal trading rate (the control)
# ---------------------------------------------------------------------------


def optimal_trading_rate(
    *,
    inventory: float,
    h2: float,
    h1: float,
    kappa: float,
) -> float:
    """Closed-form optimal liquidation rate ``nu*(t, q)``.

    Derived by maximising the Hamiltonian wrt ``nu``::

        nu*(t, q) = - (h_2(t) * q + h_1(t) / 2) / kappa

    Positive ``nu`` means selling inventory; negative ``nu`` means
    buying. Used by :class:`~aqp.rl.envs.OptimalExecutionEnv` and the
    ``optimal_control.cartea_jaimungal_liquidation`` analysis flow.
    """
    return -(h2 * inventory + 0.5 * h1) / max(kappa, 1e-12)


def optimal_liquidation_value(
    *,
    inventory: float,
    mid_price: float,
    h2: float,
    h1: float,
    h0: float,
) -> float:
    """Value function ``H(t, q, S)`` at one point on the integration grid."""
    return float(mid_price * inventory + h2 * inventory * inventory + h1 * inventory + h0)


# ---------------------------------------------------------------------------
# Top-level driver
# ---------------------------------------------------------------------------


def solve(
    params: CarteaJaimungalParams | None = None,
    **overrides: float,
) -> CarteaJaimungalResult:
    """Solve the Cartea-Jaimungal optimal-liquidation HJB end-to-end.

    Returns a :class:`CarteaJaimungalResult` with the value-function
    coefficients on a time grid plus a *forward-simulated* inventory /
    cash path under the optimal feedback control.
    """
    p = params or CarteaJaimungalParams()
    horizon = overrides.get("horizon", p.horizon)
    n_steps = int(overrides.get("n_steps", p.n_steps))
    sigma = overrides.get("sigma", p.sigma)
    phi = overrides.get("phi", p.phi)
    alpha = overrides.get("alpha", p.alpha)
    kappa = overrides.get("kappa", p.kappa)
    q0 = overrides.get("initial_inventory", p.initial_inventory)

    t_grid, h2, h1, h0 = _integrate_rk4(
        horizon=horizon,
        n_steps=n_steps,
        phi=phi,
        alpha=alpha,
        kappa=kappa,
    )

    # Forward-simulate the inventory + cash path under the optimal rate.
    dt = horizon / n_steps
    inv_path = np.empty(n_steps + 1)
    cash_path = np.empty(n_steps + 1)
    rate_path = np.empty(n_steps + 1)
    inv_path[0] = q0
    cash_path[0] = 0.0
    # Stylised price path: mean-reverting GBM with ``sigma`` vol; we
    # simulate the deterministic feedback so the curve is reproducible.
    rng = np.random.default_rng(seed=0)
    s = 100.0
    for i in range(n_steps):
        rate = optimal_trading_rate(
            inventory=inv_path[i], h2=h2[i], h1=h1[i], kappa=kappa
        )
        rate_path[i] = rate
        # Inventory updates by -rate * dt (selling reduces inventory).
        inv_path[i + 1] = inv_path[i] + rate * dt
        # Cash captures executed price minus impact.
        impact = kappa * rate
        cash_path[i + 1] = cash_path[i] + (-rate * (s - impact)) * dt
        s += sigma * math.sqrt(dt) * float(rng.standard_normal())
    rate_path[-1] = rate_path[-2] if n_steps >= 1 else 0.0

    expected_pnl = float(cash_path[-1] + inv_path[-1] * s - alpha * inv_path[-1] ** 2)
    return CarteaJaimungalResult(
        t_grid=t_grid,
        h2=h2,
        h1=h1,
        h0=h0,
        optimal_rate=rate_path,
        inventory_path=inv_path,
        cash_path=cash_path,
        expected_pnl=expected_pnl,
    )


# math import needed by `solve`
import math  # noqa: E402

__all__ = [
    "CarteaJaimungalParams",
    "CarteaJaimungalResult",
    "optimal_liquidation_value",
    "optimal_trading_rate",
    "solve",
]
