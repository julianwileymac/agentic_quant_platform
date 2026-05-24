"""Analytical optimal-execution / market-making baselines for RL agents.

This sub-package exposes the closed-form trading-strategy baselines
that RL agents in :mod:`aqp_rl.agents` use as residual-policy
priors:

- :mod:`aqp_rl.analytical.almgren_chriss` — Almgren & Chriss 2001
  optimal-execution schedule (``sinh``-trajectory + expected loss +
  loss variance).
- :mod:`aqp_rl.analytical.avellaneda_stoikov` — thin re-export of
  the JAX-compiled :mod:`aqp.optimal_control.avellaneda_stoikov`
  reservation-price + half-spread formulas.
- :mod:`aqp_rl.analytical.cartea_jaimungal` — thin re-export of
  the :mod:`aqp.optimal_control.cartea_jaimungal` HJB solver +
  optimal trading rate.

The matching residual policies live under :mod:`aqp_rl.agents`:

- :class:`aqp_rl.agents.almgren_chriss_residual.AlmgrenChrissResidualPolicy`
- :class:`aqp_rl.agents.avellaneda_stoikov_residual.AvellanedaStoikovResidualPolicy`

Hard rule 38: residual policy outputs a weight / depth vector consumed
by :class:`aqp_rl.portfolio.pipeline.WeightCentricPipeline`.
"""
from __future__ import annotations

from aqp_rl.analytical.almgren_chriss import (
    AlmgrenChrissParams,
    AlmgrenChrissSchedule,
    cost_expectation,
    cost_variance,
    kappa,
    optimal_positions,
    trade_list,
)

# Thin re-exports — both fall back to ``None`` when ``aqp`` monolith
# is unavailable (e.g. pure-`aqp_rl`-only test runs). Tests guard
# accordingly.
try:
    from aqp_rl.analytical.avellaneda_stoikov import (
        AvellanedaStoikovParams,
        compute_optimal_quotes,
    )
except Exception:  # noqa: BLE001
    AvellanedaStoikovParams = None  # type: ignore[assignment]
    compute_optimal_quotes = None  # type: ignore[assignment]

try:
    from aqp_rl.analytical.cartea_jaimungal import (
        CarteaJaimungalParams,
        optimal_trading_rate,
    )
except Exception:  # noqa: BLE001
    CarteaJaimungalParams = None  # type: ignore[assignment]
    optimal_trading_rate = None  # type: ignore[assignment]


__all__ = [
    "AlmgrenChrissParams",
    "AlmgrenChrissSchedule",
    "AvellanedaStoikovParams",
    "CarteaJaimungalParams",
    "compute_optimal_quotes",
    "cost_expectation",
    "cost_variance",
    "kappa",
    "optimal_positions",
    "optimal_trading_rate",
    "trade_list",
]
