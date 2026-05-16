"""Avellaneda-Stoikov (2008) market-making model.

The canonical reference: M. Avellaneda and S. Stoikov, "High-frequency
trading in a limit order book", *Quantitative Finance* 8 (3), 217-224.
We also expose the closed-form Guéant-Lehalle-Fernandez-Tapia (GLFT,
2013) approximation used by ``aqp.strategies.hft.alphas.GLFTMM``.

The model in two equations
==========================

Reservation (fair) price::

    r(s, q, t) = s - q * gamma * sigma**2 * (T - t)

Optimal half-spread::

    delta = gamma * sigma**2 * (T - t) + (2 / gamma) * ln(1 + gamma / k)

where:

- ``s`` — mid price.
- ``q`` — current inventory (positive = long).
- ``gamma`` — risk-aversion coefficient (penalises inventory variance).
- ``sigma`` — volatility of the mid-price.
- ``k`` — order-book liquidity parameter (Cox-process intensity decay).
- ``T - t`` — time to terminal (close-of-day) horizon.

The market maker quotes ``bid = r - delta`` and ``ask = r + delta``.

JAX compilation
===============

:func:`compute_optimal_quotes` is JIT-compiled with ``@jax.jit``. It
takes only Python floats / JAX arrays — no Python control flow keyed on
the values, no I/O. That lets the analysis-flow runner call it inside a
``vmap`` across the inventory grid without recompiling.

When JAX is not installed (the ``optimal-control`` extra is missing) the
module exposes the same functions backed by NumPy so the rest of AQP
keeps importing cleanly. Performance drops by ~30x in that case but
correctness is identical.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JAX import shim — degrade gracefully when the optional extra is missing.
# ---------------------------------------------------------------------------

try:
    import jax  # type: ignore[import-not-found]
    import jax.numpy as jnp  # type: ignore[import-not-found]

    _JAX_AVAILABLE = True
except Exception:  # noqa: BLE001
    jax = None  # type: ignore[assignment]
    jnp = np  # type: ignore[assignment]
    _JAX_AVAILABLE = False


def _jit_or_passthrough(fn: Any) -> Any:
    """Apply ``jax.jit`` if JAX is installed, else return the function as-is."""
    if _JAX_AVAILABLE:
        return jax.jit(fn)  # type: ignore[union-attr]
    return fn


# ---------------------------------------------------------------------------
# Public params / result containers (Pydantic-free for JAX compatibility).
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class AvellanedaStoikovParams:
    """All knobs for a single AvSt quote computation.

    The defaults are sane for an equity LOB with second-frequency mid
    samples; tune ``gamma`` for inventory aggression and ``k`` for
    order-arrival rate.
    """

    gamma: float = 0.1
    """Risk aversion. Higher = more aggressive inventory unwinding."""

    sigma: float = 0.01
    """Mid-price volatility (per unit of ``T-t``)."""

    k: float = 1.5
    """Cox-process liquidity parameter (1 / typical order-decay scale)."""

    T_minus_t: float = 1.0
    """Time-to-horizon in the same units as ``sigma``."""

    inventory_cap: float = 100.0
    """Hard cap on absolute inventory (drives quote suspension)."""


@dataclass(slots=True, frozen=True)
class AvellanedaStoikovResult:
    """Output of a single AvSt quote computation."""

    reservation_price: float
    half_spread: float
    bid: float
    ask: float
    inventory: float

    def to_dict(self) -> dict[str, float]:
        return {
            "reservation_price": float(self.reservation_price),
            "half_spread": float(self.half_spread),
            "bid": float(self.bid),
            "ask": float(self.ask),
            "inventory": float(self.inventory),
        }


# ---------------------------------------------------------------------------
# Pure JAX-compatible numeric core (no I/O, no Python branching on values).
# ---------------------------------------------------------------------------


def _avst_kernel(
    mid_price: Any,
    inventory: Any,
    gamma: Any,
    sigma: Any,
    k: Any,
    T_minus_t: Any,
) -> tuple[Any, Any, Any, Any]:
    """Compute reservation price + half-spread in pure JAX/NumPy ops.

    Inputs may be scalar floats or shape-compatible arrays — the math
    broadcasts. Output tuple matches the order ``(r, delta, bid, ask)``.
    """
    sigma_sq_dt = sigma * sigma * T_minus_t
    reservation = mid_price - inventory * gamma * sigma_sq_dt
    half_spread = 0.5 * gamma * sigma_sq_dt + (1.0 / gamma) * jnp.log(
        1.0 + gamma / jnp.maximum(k, 1e-12)
    )
    bid = reservation - half_spread
    ask = reservation + half_spread
    return reservation, half_spread, bid, ask


_avst_kernel_jit = _jit_or_passthrough(_avst_kernel)


# ---------------------------------------------------------------------------
# Public single-call API — returns a Python dataclass for ergonomics.
# ---------------------------------------------------------------------------


def compute_optimal_quotes(
    mid_price: float,
    inventory: float,
    params: AvellanedaStoikovParams | None = None,
    *,
    gamma: float | None = None,
    sigma: float | None = None,
    k: float | None = None,
    T_minus_t: float | None = None,
) -> AvellanedaStoikovResult:
    """Compute AvSt optimal bid / ask quotes for a single ``(mid, inventory)``.

    Either pass a fully-formed :class:`AvellanedaStoikovParams` or
    override individual knobs as keyword arguments. The latter is what
    the analysis-flow runner uses; the former is what
    ``aqp.strategies.hft.alphas.AvellanedaStoikovMM`` uses.
    """
    p = params or AvellanedaStoikovParams()
    g = gamma if gamma is not None else p.gamma
    s = sigma if sigma is not None else p.sigma
    kk = k if k is not None else p.k
    dt = T_minus_t if T_minus_t is not None else p.T_minus_t

    r, delta, bid, ask = _avst_kernel_jit(
        float(mid_price), float(inventory), float(g), float(s), float(kk), float(dt)
    )
    # Convert from 0-D JAX/NumPy array to Python float for the dataclass.
    return AvellanedaStoikovResult(
        reservation_price=float(r),
        half_spread=float(delta),
        bid=float(bid),
        ask=float(ask),
        inventory=float(inventory),
    )


def quote_grid(
    mid_price: float,
    inventory_grid: np.ndarray,
    params: AvellanedaStoikovParams,
) -> dict[str, np.ndarray]:
    """Vectorised AvSt quote schedule across an inventory grid.

    Returns a dict with arrays of shape ``(len(inventory_grid),)`` for
    ``reservation_price``, ``half_spread``, ``bid``, ``ask``. Used by
    ``aqp.analysis.flows.optimal_control.avellaneda_stoikov_quotes``.
    """
    inv = np.asarray(inventory_grid, dtype=float)
    if _JAX_AVAILABLE:
        # vmap across inventory; everything else is scalar/broadcast.
        kernel = jax.vmap(  # type: ignore[union-attr]
            _avst_kernel,
            in_axes=(None, 0, None, None, None, None),
        )
        r, delta, bid, ask = kernel(
            float(mid_price),
            jnp.asarray(inv),
            float(params.gamma),
            float(params.sigma),
            float(params.k),
            float(params.T_minus_t),
        )
        return {
            "inventory": np.asarray(inv),
            "reservation_price": np.asarray(r),
            "half_spread": np.asarray(delta),
            "bid": np.asarray(bid),
            "ask": np.asarray(ask),
        }
    # NumPy fallback — explicit broadcast.
    r, delta, bid, ask = _avst_kernel(
        float(mid_price),
        inv,
        float(params.gamma),
        float(params.sigma),
        float(params.k),
        float(params.T_minus_t),
    )
    return {
        "inventory": inv,
        "reservation_price": np.asarray(r),
        "half_spread": np.asarray(delta) * np.ones_like(inv),  # half-spread is scalar in input
        "bid": np.asarray(bid),
        "ask": np.asarray(ask),
    }


# ---------------------------------------------------------------------------
# GLFT (Guéant-Lehalle-Fernandez-Tapia 2013) closed-form
# ---------------------------------------------------------------------------


def glft_closed_form(
    mid_price: float,
    inventory: float,
    gamma: float,
    sigma: float,
    kappa: float,
    *,
    horizon: float = 1.0,
) -> AvellanedaStoikovResult:
    """Steady-state GLFT 2013 closed-form quotes.

    Differs from :func:`compute_optimal_quotes` by treating ``T-t`` as a
    long-horizon limit and using a slightly different log term — this
    matches the closed form documented in Guéant et al. eq. (4.3).

    Used by :class:`aqp.strategies.hft.alphas.GLFTMM` so the per-bar
    ``on_event`` body can stay pure-Python and import-cheap.
    """
    sigma_sq = sigma * sigma * horizon
    reservation = mid_price - inventory * gamma * sigma_sq
    half_spread = gamma * sigma_sq + (2.0 / gamma) * math.log(
        1.0 + gamma / max(kappa, 1e-12)
    )
    return AvellanedaStoikovResult(
        reservation_price=float(reservation),
        half_spread=float(half_spread),
        bid=float(reservation - half_spread),
        ask=float(reservation + half_spread),
        inventory=float(inventory),
    )


__all__ = [
    "AvellanedaStoikovParams",
    "AvellanedaStoikovResult",
    "compute_optimal_quotes",
    "glft_closed_form",
    "quote_grid",
]
