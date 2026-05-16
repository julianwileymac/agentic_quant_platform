"""Optimal-control / HJB math layer for AQP.

This package hosts the JAX-compiled implementations of the canonical
high-frequency optimal-control models:

- :mod:`aqp.optimal_control.avellaneda_stoikov` — single-asset
  inventory-aware market-making quotes (Avellaneda & Stoikov 2008).
- :mod:`aqp.optimal_control.cartea_jaimungal` — finite-time inventory-
  penalised optimal liquidation + market making
  (Cartea, Jaimungal, & Penalva 2015 ch. 8/10).
- :mod:`aqp.optimal_control.hjb_solver` — thin convenience layer with
  ``solve_avst`` / ``solve_cj`` / ``value_function_to_arrow`` helpers
  that coerce JAX outputs into pyarrow tables for Iceberg gold-tier
  writes through :class:`~aqp.analysis.runtime.AnalysisRuntime`.

JAX is the only fast-path numerics here. Every solver function is pure
(no I/O, no globals, no module-level RNG) and JIT-compiled with
``@jax.jit`` so the analysis-flow runner can call them in tight loops
without Python interpreter overhead.

If JAX is not installed, the module imports cleanly but the solver
functions raise an informative ``ImportError`` on first call. Run
``pip install -e ".[optimal-control]"`` to enable the fast path.
"""
from __future__ import annotations

from aqp.optimal_control.avellaneda_stoikov import (
    AvellanedaStoikovParams,
    AvellanedaStoikovResult,
    compute_optimal_quotes,
    glft_closed_form,
)
from aqp.optimal_control.cartea_jaimungal import (
    CarteaJaimungalParams,
    CarteaJaimungalResult,
    optimal_liquidation_value,
    optimal_trading_rate,
)
from aqp.optimal_control.hjb_solver import (
    solve_avst,
    solve_cj,
    value_function_to_arrow,
)

__all__ = [
    "AvellanedaStoikovParams",
    "AvellanedaStoikovResult",
    "CarteaJaimungalParams",
    "CarteaJaimungalResult",
    "compute_optimal_quotes",
    "glft_closed_form",
    "optimal_liquidation_value",
    "optimal_trading_rate",
    "solve_avst",
    "solve_cj",
    "value_function_to_arrow",
]
