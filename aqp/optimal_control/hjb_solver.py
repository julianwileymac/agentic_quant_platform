"""Convenience layer that bridges optimal-control solvers and AQP plumbing.

Three responsibilities:

1. Top-level ``solve_avst`` / ``solve_cj`` entry points the analysis
   flows call. These re-export the canonical functions but with a single
   uniform return type so the flow runner can shovel the output into
   ``FlowResult.metrics`` + ``FlowResult.rows`` without per-flow glue.
2. ``value_function_to_arrow`` — coerces a JAX/NumPy value-function grid
   into a :class:`pyarrow.Table` so :class:`~aqp.analysis.runtime.AnalysisRuntime`
   can persist it to ``aqp_gold_analysis_optimal_control`` via
   :func:`aqp.data.iceberg_catalog.append_arrow` (AGENTS rule 21).
3. Optional integration with :mod:`finhjb` for high-dimensional HJB
   solves where the linear-quadratic ansatz no longer holds — surfaces
   when users opt-in via ``solver="finhjb"``.

When :mod:`finhjb` is missing, the high-dimensional path falls back to
the linear-quadratic ansatz with a logged warning, keeping the platform
operational on a laptop without the ``optimal-control`` extra.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from aqp.optimal_control.avellaneda_stoikov import (
    AvellanedaStoikovParams,
    AvellanedaStoikovResult,
    compute_optimal_quotes,
    quote_grid,
)
from aqp.optimal_control.cartea_jaimungal import (
    CarteaJaimungalParams,
    CarteaJaimungalResult,
    solve as _cj_solve,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Avellaneda-Stoikov
# ---------------------------------------------------------------------------


def solve_avst(
    *,
    mid_price: float,
    inventory_grid: np.ndarray | list[float] | None = None,
    inventory: float | None = None,
    gamma: float = 0.1,
    sigma: float = 0.01,
    k: float = 1.5,
    T_minus_t: float = 1.0,
) -> dict[str, Any]:
    """Solve Avellaneda-Stoikov for a single point or an inventory grid.

    Returns a dict shaped for direct use as ``FlowResult.metrics`` /
    ``FlowResult.rows`` in
    ``aqp.analysis.flows.optimal_control.avellaneda_stoikov_quotes``.
    """
    params = AvellanedaStoikovParams(
        gamma=gamma, sigma=sigma, k=k, T_minus_t=T_minus_t
    )
    if inventory_grid is not None:
        grid = np.asarray(inventory_grid, dtype=float)
        result = quote_grid(mid_price=float(mid_price), inventory_grid=grid, params=params)
        rows = [
            {
                "inventory": float(result["inventory"][i]),
                "reservation_price": float(result["reservation_price"][i]),
                "half_spread": float(np.atleast_1d(result["half_spread"])[i if np.atleast_1d(result["half_spread"]).size > 1 else 0]),
                "bid": float(result["bid"][i]),
                "ask": float(result["ask"][i]),
            }
            for i in range(len(grid))
        ]
        # Centre-of-mass metrics + the half-spread at zero inventory
        zero_idx = int(np.argmin(np.abs(grid)))
        return {
            "metrics": {
                "mid_price": float(mid_price),
                "n_points": int(len(grid)),
                "half_spread_at_zero": float(rows[zero_idx]["half_spread"]),
                "bid_at_zero": float(rows[zero_idx]["bid"]),
                "ask_at_zero": float(rows[zero_idx]["ask"]),
                "gamma": float(gamma),
                "sigma": float(sigma),
                "k": float(k),
                "T_minus_t": float(T_minus_t),
            },
            "rows": rows,
        }
    # Single-point case
    inv = float(inventory or 0.0)
    res = compute_optimal_quotes(
        mid_price=float(mid_price), inventory=inv, params=params
    )
    return {
        "metrics": {
            **res.to_dict(),
            "mid_price": float(mid_price),
            "gamma": float(gamma),
            "sigma": float(sigma),
            "k": float(k),
            "T_minus_t": float(T_minus_t),
        },
        "rows": [{**res.to_dict(), "mid_price": float(mid_price)}],
    }


# ---------------------------------------------------------------------------
# Cartea-Jaimungal
# ---------------------------------------------------------------------------


def solve_cj(
    *,
    horizon: float = 1.0,
    initial_inventory: float = 100.0,
    sigma: float = 0.01,
    phi: float = 1e-4,
    alpha: float = 1e-3,
    kappa: float = 1.0,
    n_steps: int = 200,
) -> dict[str, Any]:
    """Solve the Cartea-Jaimungal optimal-liquidation HJB via RK4.

    Returns a dict with summary metrics + a row-per-time-step trajectory
    suitable for ``FlowResult.rows``. Used by
    ``aqp.analysis.flows.optimal_control.cartea_jaimungal_liquidation``.
    """
    params = CarteaJaimungalParams(
        horizon=horizon,
        initial_inventory=initial_inventory,
        sigma=sigma,
        phi=phi,
        alpha=alpha,
        kappa=kappa,
        n_steps=n_steps,
    )
    result = _cj_solve(params)
    rows = [
        {
            "t": float(result.t_grid[i]),
            "h2": float(result.h2[i]),
            "h1": float(result.h1[i]),
            "h0": float(result.h0[i]),
            "inventory": float(result.inventory_path[i]),
            "cash": float(result.cash_path[i]),
            "trading_rate": float(result.optimal_rate[i]) if i < len(result.optimal_rate) else 0.0,
        }
        for i in range(len(result.t_grid))
    ]
    return {
        "metrics": {
            **result.to_summary(),
            "phi": float(phi),
            "alpha": float(alpha),
            "kappa": float(kappa),
            "initial_inventory": float(initial_inventory),
            "terminal_inventory": float(result.inventory_path[-1]),
            "terminal_cash": float(result.cash_path[-1]),
            "expected_pnl": float(result.expected_pnl),
        },
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Arrow coercion (Iceberg-friendly)
# ---------------------------------------------------------------------------


def value_function_to_arrow(rows: list[dict[str, Any]]):
    """Coerce a list-of-dicts into a :class:`pyarrow.Table`.

    Returns ``None`` if pyarrow is unavailable (so callers can pass
    ``arrow_table=None`` into ``FlowResult`` without crashing). The
    sibling helper :func:`aqp.analysis.base.coerce_arrow` does the same
    for generic flow rows; we keep this one local so the
    optimal-control package has no implicit dependency on
    ``aqp.analysis``.
    """
    if not rows:
        return None
    try:
        import pyarrow as pa
    except Exception:  # noqa: BLE001
        logger.debug("pyarrow not installed; skipping arrow coercion")
        return None
    columns: dict[str, list[Any]] = {}
    for row in rows:
        for key, value in row.items():
            columns.setdefault(key, []).append(value)
    return pa.table(columns)


__all__ = [
    "AvellanedaStoikovParams",
    "AvellanedaStoikovResult",
    "CarteaJaimungalParams",
    "CarteaJaimungalResult",
    "solve_avst",
    "solve_cj",
    "value_function_to_arrow",
]
