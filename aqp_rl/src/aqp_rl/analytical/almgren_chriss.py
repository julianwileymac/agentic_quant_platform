"""Almgren & Chriss (2001) optimal-execution closed forms.

Canonical reference: R. Almgren and N. Chriss, "Optimal execution of
portfolio transactions", *Journal of Risk* 3 (2), 5-39 (2001).

The model
=========

A block of ``X`` shares must be liquidated over horizon ``T`` in
``N`` equal-length steps of duration ``τ = T / N``. The optimal
trade schedule trades off temporary market impact (per-step cost
``η · (n_k / τ)``) against price-variance risk (``λ · σ² ·
Σ_k x_k² · τ``) where:

- ``γ`` is the permanent-impact slope (dollars-per-share-traded).
- ``η`` is the temporary-impact slope (the agent eats ``η`` of the
  available liquidity per unit of trading rate).
- ``ε`` is the per-share fixed cost (half the bid-ask spread).
- ``σ`` is the absolute mid-price volatility (dollars / sqrt(time)).
- ``λ`` is the trader's risk-aversion coefficient.

Define the effective temporary impact::

    η̃ = η − γ · τ / 2

and the decay rate::

    κ² = λ · σ² / η̃

The optimal schedule (equation 18 of the paper) is::

    n_k = (2 · sinh(κ·τ/2) / sinh(κ·T)) · cosh(κ · (T − (k − 1/2)·τ)) · X
                                              for k = 1, …, N

with positions after trade ``k``::

    x_k = sinh(κ · (T − k·τ)) / sinh(κ·T) · X

Expected execution cost (equation 20)::

    E[loss] = γ·X²/2 + ε·X + (η̃ / τ) · Σ_k n_k²

Loss variance (equation 21)::

    V[loss] = σ² · τ · Σ_k x_k²

Worked example from the paper §2 ("We have chosen γ = 2.5·10⁻⁷,
η = 2.5·10⁻⁶, ε = 0.0625, σ = 0.95 dollars / sqrt(day), λ = 10⁻⁶";
``X = 10⁶`` shares over 5 days) yields ``κ ≈ 0.6 / day``. The unit
tests in :mod:`tests.analytical.test_almgren_chriss` lock that in.

Hard rule 38: residual policies built on top of this schedule emit
target weights / target positions to the
:class:`aqp_rl.portfolio.pipeline.WeightCentricPipeline`.

The module is pure-NumPy; no JAX dependency.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(slots=True, frozen=True)
class AlmgrenChrissParams:
    """All knobs for one Almgren-Chriss optimal-liquidation computation.

    Defaults match the paper's §2 worked example so a bare
    ``AlmgrenChrissParams()`` instantiates a sanity-check schedule
    with the published ``κ ≈ 0.6 / day``.
    """

    total_shares: float = 1_000_000.0
    """Total block size ``X`` (positive = liquidation, negative = acquisition)."""

    liquidation_time: float = 5.0
    """Total horizon ``T`` in the canonical unit (days for paper example)."""

    num_trades: int = 5
    """Number of evenly-spaced trades ``N``."""

    gamma: float = 2.5e-7
    """Permanent-impact slope (dollars per share traded)."""

    eta: float = 2.5e-6
    """Temporary-impact slope (dollars per (share / time))."""

    epsilon: float = 0.0625
    """Fixed per-share cost (typically half the bid-ask spread)."""

    sigma: float = 0.95
    """Mid-price volatility in dollars per sqrt(time unit)."""

    risk_aversion: float = 1e-6
    """Trader's risk-aversion coefficient ``λ``. The paper uses 10⁻⁶."""

    @property
    def tau(self) -> float:
        """Per-step length ``τ = T / N``."""
        if self.num_trades <= 0:
            raise ValueError("num_trades must be > 0")
        return float(self.liquidation_time) / float(self.num_trades)

    @property
    def eta_tilde(self) -> float:
        """Effective temporary impact ``η̃ = η − γ · τ / 2``.

        Raises :class:`ValueError` when ``η̃`` would be non-positive
        (the model is undefined when temporary impact is dominated by
        permanent impact at the chosen step length).
        """
        et = self.eta - 0.5 * self.gamma * self.tau
        if et <= 0:
            raise ValueError(
                f"Effective temporary impact η̃={et!r} must be > 0; "
                f"reduce τ (= {self.tau!r}) or increase η (= {self.eta!r})."
            )
        return float(et)


@dataclass(slots=True)
class AlmgrenChrissSchedule:
    """Container bundling the four primary outputs of the AC closed forms.

    Used so callers don't have to recompute ``κ`` / positions when
    they want the trade list AND the expected cost.

    Attributes
    ----------
    kappa:
        Decay rate ``κ`` in inverse-time units (``1 / day`` for the
        paper example).
    trades:
        ``(N,)`` array of per-step trade sizes ``n_k`` for ``k=1..N``.
        Always nonnegative for a liquidation (positive ``total_shares``);
        the sign-convention for an acquisition matches ``total_shares``.
    positions:
        ``(N+1,)`` array of holdings ``x_0, x_1, …, x_N`` so the user
        can plot the trajectory.
    expected_cost:
        Closed-form ``E[loss]``.
    cost_variance:
        Closed-form ``V[loss]``.
    """

    kappa: float
    trades: np.ndarray
    positions: np.ndarray
    expected_cost: float
    cost_variance: float
    extras: dict[str, Any] = field(default_factory=dict)


def kappa(params: AlmgrenChrissParams) -> float:
    """Compute the decay rate ``κ = sqrt(λ · σ² / η̃)``."""
    κ_sq = params.risk_aversion * params.sigma * params.sigma / params.eta_tilde
    if κ_sq <= 0:
        raise ValueError(
            f"κ² = {κ_sq!r} must be > 0; check sign of risk_aversion / sigma."
        )
    return float(math.sqrt(κ_sq))


def optimal_positions(params: AlmgrenChrissParams) -> np.ndarray:
    """Return holdings ``x_0, x_1, …, x_N`` (length ``N+1``).

    ``x_0 = X`` (full block at start), ``x_N = 0`` (flat at horizon).
    The intermediate positions follow ``x_k = sinh(κ·(T−k·τ)) / sinh(κ·T) · X``.
    """
    κ = kappa(params)
    τ = params.tau
    T = params.liquidation_time
    N = params.num_trades
    X = params.total_shares
    sinh_kT = math.sinh(κ * T)
    if sinh_kT == 0:
        # Trivial degenerate case (κ·T = 0) — uniform liquidation.
        return X * (1.0 - np.arange(N + 1, dtype=np.float64) / N)
    k = np.arange(N + 1, dtype=np.float64)
    x = np.sinh(κ * (T - k * τ)) / sinh_kT * X
    x[N] = 0.0  # numerical clean-up — sinh(0) is exactly 0 anyway.
    return x


def trade_list(params: AlmgrenChrissParams) -> np.ndarray:
    """Return optimal trade schedule ``n_k`` for ``k=1..N`` (length ``N``).

    Equation 18 of Almgren & Chriss 2001. ``trades[i]`` is the trade
    sent at the start of step ``i+1`` (i.e. ``n_1, n_2, …, n_N``).

    The cumulative sum of :func:`trade_list` exactly equals the
    initial block size:: ``np.sum(trade_list(p)) == p.total_shares``.
    This is asserted in :mod:`tests.analytical.test_almgren_chriss`.
    """
    x = optimal_positions(params)
    # n_k = x_{k-1} − x_k for k = 1..N.
    return x[:-1] - x[1:]


def cost_expectation(params: AlmgrenChrissParams) -> float:
    """Closed-form expected execution cost ``E[loss]`` (Almgren-Chriss eq. 20).

    The expectation has three contributions:

    1. ``γ · X² / 2`` — permanent-impact cost on the residual book.
    2. ``ε · X`` — fixed per-share spread cost summed over the block.
    3. ``(η̃ / τ) · Σ_k n_k²`` — sum of squared temporary-impact costs.
    """
    n = trade_list(params)
    γ = params.gamma
    ε = params.epsilon
    X = abs(params.total_shares)
    τ = params.tau
    η̃ = params.eta_tilde
    permanent = 0.5 * γ * X * X
    fixed = ε * X
    temporary = (η̃ / τ) * float(np.sum(n * n))
    return float(permanent + fixed + temporary)


def cost_variance(params: AlmgrenChrissParams) -> float:
    """Closed-form variance of execution cost ``V[loss]`` (eq. 21).

    ``V[loss] = σ² · τ · Σ_k x_k²`` where the sum runs over the
    *holdings* ``x_k`` for ``k=1..N`` (the position carried through
    the volatility window for each step).
    """
    x = optimal_positions(params)
    # Variance accumulates over the holdings between trades, indexed
    # k=1..N (the position held during step k).
    σ = params.sigma
    τ = params.tau
    holdings_squared_sum = float(np.sum(x[1:] * x[1:]))
    return float(σ * σ * τ * holdings_squared_sum)


def build_schedule(params: AlmgrenChrissParams) -> AlmgrenChrissSchedule:
    """One-shot helper: compute κ + trades + positions + E[loss] + V[loss]."""
    κ = kappa(params)
    x = optimal_positions(params)
    n = x[:-1] - x[1:]
    γ = params.gamma
    ε = params.epsilon
    X = abs(params.total_shares)
    τ = params.tau
    η̃ = params.eta_tilde
    e_loss = 0.5 * γ * X * X + ε * X + (η̃ / τ) * float(np.sum(n * n))
    v_loss = float(params.sigma * params.sigma * τ * np.sum(x[1:] * x[1:]))
    return AlmgrenChrissSchedule(
        kappa=κ,
        trades=n,
        positions=x,
        expected_cost=e_loss,
        cost_variance=v_loss,
        extras={"tau": τ, "eta_tilde": η̃},
    )


__all__ = [
    "AlmgrenChrissParams",
    "AlmgrenChrissSchedule",
    "build_schedule",
    "cost_expectation",
    "cost_variance",
    "kappa",
    "optimal_positions",
    "trade_list",
]
