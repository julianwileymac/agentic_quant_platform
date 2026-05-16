"""Lucic-Tse (2024-2026) portfolio-level options market-making framework.

References:

- V. Lucic and A. Tse, "Optimal option market making and volatility
  arbitrage", *SSRN preprint* + *Risk.net* 2024-2026.
- B. Baldacci, P. Bergault, O. Guéant, "Algorithmic market making for
  options", *Quantitative Finance* 2021 — earlier multi-strike
  approximation.

The model in two equations
==========================

Per-strike-and-expiry alpha (volatility arbitrage profit)::

    alpha(K, T) = 0.5 * S**2 * Gamma(K, T) * (sigma_real**2 - sigma_imp**2)

where ``Gamma`` is the option Gamma. This is the option-equivalent of
the spot-vol-arbitrage edge and is the dominant term in the optimal
quote.

Inventory-skewed bid/ask quote::

    bid(K, T) = mid(K, T) - half_spread(K, T) - inventory_skew(K, T)
    ask(K, T) = mid(K, T) + half_spread(K, T) - inventory_skew(K, T)

with ``inventory_skew`` and ``half_spread`` solved from the linear-
quadratic Riccati ODE that the Lucic-Tse paper derives. The full ODE
admits a closed-form steady-state solution under the standard regularity
assumptions; we implement that closed form here.

Closed-form Riccati steady-state
================================

Let:

- ``Vega(K, T)`` — vega of each option in the chain.
- ``q(K, T)`` — current inventory at strike K, expiry T.
- ``gamma_inv`` — inventory penalty coefficient (chain-wide).
- ``hedge_cost`` — cost of delta-hedging the running inventory.

Then under the steady-state ansatz the Riccati equation collapses to::

    inventory_skew(K, T) = gamma_inv * (Vega(K, T) @ Sigma_vol @ q)
    half_spread(K, T) = base_spread + 0.5 * hedge_cost * |Gamma(K, T)|

where ``Sigma_vol`` is the covariance matrix of the implied-volatility
factors (rank-reduced via PCA in production; we accept it as an input
here so the analysis flow can pass either an identity or a pre-computed
factor model).

JAX implementation
==================

Every routine takes JAX arrays and uses ``jnp.einsum`` for the matrix
contractions, so the analysis-flow runner can ``vmap`` across whole
option chains without Python interpreter overhead. No ``for`` loops
appear inside any of the math functions.

When JAX is missing, the module falls back to NumPy with the same API
and identical numerical results.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

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
# Public params + result containers
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class LucicTseParams:
    """Knobs for a Lucic-Tse portfolio MM run."""

    gamma_inv: float = 0.05
    """Chain-wide inventory penalty coefficient."""

    base_spread: float = 0.05
    """Minimum half-spread regardless of vol-arb edge (covers exchange fees + slippage)."""

    hedge_cost: float = 0.001
    """Cost of one unit of delta-hedge rebalancing (bps)."""

    vol_factor_count: int = 0
    """If > 0, the runner reduces ``Sigma_vol`` to this many PCA factors."""


@dataclass(slots=True)
class LucicTseQuotes:
    """Output of one portfolio-quoting step."""

    bid: np.ndarray
    """Bid prices, shape ``(n_expiries, n_strikes)``."""

    ask: np.ndarray
    """Ask prices, shape ``(n_expiries, n_strikes)``."""

    half_spread: np.ndarray
    """Half-spreads, shape ``(n_expiries, n_strikes)``."""

    inventory_skew: np.ndarray
    """Quote skew applied to bid+ask, shape ``(n_expiries, n_strikes)``."""

    expected_pnl: np.ndarray
    """Per-strike expected vol-arb PnL, shape ``(n_expiries, n_strikes)``."""

    total_expected_pnl: float
    """Sum of ``expected_pnl`` across the whole chain."""

    def to_summary(self) -> dict[str, float]:
        return {
            "n_strikes": int(self.bid.shape[1]) if self.bid.ndim >= 2 else 0,
            "n_expiries": int(self.bid.shape[0]) if self.bid.ndim >= 1 else 0,
            "total_expected_pnl": float(self.total_expected_pnl),
            "max_half_spread": float(np.asarray(self.half_spread).max()) if self.half_spread.size else 0.0,
            "min_half_spread": float(np.asarray(self.half_spread).min()) if self.half_spread.size else 0.0,
            "max_inventory_skew": float(np.asarray(self.inventory_skew).max()) if self.inventory_skew.size else 0.0,
        }


# ---------------------------------------------------------------------------
# Pure-functional kernels (jnp.einsum + broadcasted ops only).
# ---------------------------------------------------------------------------


def _expected_vol_arb_pnl(
    spot,
    gamma_surface,
    realized_vol,
    implied_vol,
):
    """Lucic-Tse expected vol-arb PnL per strike/expiry.

    All inputs are 2-D arrays of shape ``(n_expiries, n_strikes)``
    (broadcasting handles realized_vol / spot if scalar).

    Formula::

        alpha = 0.5 * S**2 * Gamma * (sigma_real**2 - sigma_imp**2)
    """
    return 0.5 * (spot * spot) * gamma_surface * (realized_vol * realized_vol - implied_vol * implied_vol)


def _inventory_skew_kernel(
    vega_surface,
    inventory,
    sigma_vol,
    gamma_inv,
):
    """Closed-form steady-state Riccati inventory skew.

    ``vega_surface`` and ``inventory`` are shape ``(E, K)``; ``sigma_vol``
    is shape ``(E, E)`` (vol-factor covariance across maturities). The
    skew is computed via two einsums:

    1. ``Sigma_vol @ inventory_per_expiry`` (sum across strikes first to
       collapse to per-expiry inventory).
    2. ``vega_surface * (Sigma_vol @ inv_per_expiry)`` broadcast back to
       per-strike skews.
    """
    # Per-expiry inventory: sum across strikes
    inv_per_expiry = jnp.einsum("ek->e", inventory)
    # Apply factor covariance
    risk_per_expiry = jnp.einsum("ef,f->e", sigma_vol, inv_per_expiry)
    # Multiply back into the strike grid via vega
    skew = gamma_inv * vega_surface * risk_per_expiry[:, None]
    return skew


def _half_spread_kernel(
    gamma_surface,
    base_spread,
    hedge_cost,
):
    """Closed-form half-spread::

        delta = base_spread + 0.5 * hedge_cost * |Gamma|
    """
    return base_spread + 0.5 * hedge_cost * jnp.abs(gamma_surface)


def _quote_kernel(
    spot,
    mid_quotes,
    gamma_surface,
    vega_surface,
    realized_vol,
    implied_vol,
    inventory,
    sigma_vol,
    gamma_inv,
    base_spread,
    hedge_cost,
):
    """Combined kernel returning ``(bid, ask, half_spread, skew, pnl)``.

    Pure JAX-compatible math; no Python control flow keyed on values.
    """
    pnl = _expected_vol_arb_pnl(spot, gamma_surface, realized_vol, implied_vol)
    skew = _inventory_skew_kernel(vega_surface, inventory, sigma_vol, gamma_inv)
    half_spread = _half_spread_kernel(gamma_surface, base_spread, hedge_cost)
    bid = mid_quotes - half_spread - skew
    ask = mid_quotes + half_spread - skew
    return bid, ask, half_spread, skew, pnl


_quote_kernel_jit = (
    jax.jit(_quote_kernel) if _JAX_AVAILABLE else _quote_kernel  # type: ignore[union-attr]
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_lucic_tse_quotes(
    *,
    spot: float,
    mid_quotes: np.ndarray,
    gamma_surface: np.ndarray,
    vega_surface: np.ndarray,
    realized_vol: np.ndarray | float,
    implied_vol: np.ndarray,
    inventory: np.ndarray | None = None,
    sigma_vol: np.ndarray | None = None,
    params: LucicTseParams | None = None,
) -> LucicTseQuotes:
    """Compute the Lucic-Tse optimal bid/ask quote matrix for an option chain.

    Shapes:

    - ``mid_quotes``, ``gamma_surface``, ``vega_surface``,
      ``implied_vol``, ``inventory`` — ``(n_expiries, n_strikes)``.
    - ``realized_vol`` — scalar or ``(n_expiries, n_strikes)``.
    - ``sigma_vol`` — ``(n_expiries, n_expiries)`` factor covariance.
      Defaults to identity when omitted.

    Returns a :class:`LucicTseQuotes` with bid/ask matrices + a summary
    dict ready for ``FlowResult.metrics``.
    """
    p = params or LucicTseParams()
    mid = jnp.asarray(np.asarray(mid_quotes, dtype=float))
    g = jnp.asarray(np.asarray(gamma_surface, dtype=float))
    v = jnp.asarray(np.asarray(vega_surface, dtype=float))
    iv = jnp.asarray(np.asarray(implied_vol, dtype=float))

    rv_arr = np.asarray(realized_vol, dtype=float)
    if rv_arr.ndim == 0:
        rv = jnp.broadcast_to(jnp.asarray(rv_arr), mid.shape)
    else:
        rv = jnp.asarray(rv_arr)

    if inventory is None:
        inv = jnp.zeros_like(mid)
    else:
        inv = jnp.asarray(np.asarray(inventory, dtype=float))

    n_expiries = int(mid.shape[0]) if mid.ndim >= 1 else 1
    if sigma_vol is None:
        sv = jnp.asarray(np.eye(n_expiries, dtype=float))
    else:
        sv = jnp.asarray(np.asarray(sigma_vol, dtype=float))

    bid, ask, half_spread, skew, pnl = _quote_kernel_jit(
        float(spot), mid, g, v, rv, iv, inv, sv,
        float(p.gamma_inv), float(p.base_spread), float(p.hedge_cost),
    )

    pnl_np = np.asarray(pnl)
    return LucicTseQuotes(
        bid=np.asarray(bid),
        ask=np.asarray(ask),
        half_spread=np.asarray(half_spread),
        inventory_skew=np.asarray(skew),
        expected_pnl=pnl_np,
        total_expected_pnl=float(pnl_np.sum()),
    )


def expected_vol_arb_pnl(
    *,
    spot: float,
    gamma_surface: np.ndarray,
    realized_vol: np.ndarray | float,
    implied_vol: np.ndarray,
) -> np.ndarray:
    """Standalone vol-arb PnL helper (numpy-friendly)."""
    g = jnp.asarray(np.asarray(gamma_surface, dtype=float))
    iv = jnp.asarray(np.asarray(implied_vol, dtype=float))
    rv_arr = np.asarray(realized_vol, dtype=float)
    if rv_arr.ndim == 0:
        rv = jnp.broadcast_to(jnp.asarray(rv_arr), g.shape)
    else:
        rv = jnp.asarray(rv_arr)
    return np.asarray(_expected_vol_arb_pnl(float(spot), g, rv, iv))


__all__ = [
    "LucicTseParams",
    "LucicTseQuotes",
    "compute_lucic_tse_quotes",
    "expected_vol_arb_pnl",
]
