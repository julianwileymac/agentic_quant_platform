"""Options pricing & analytics — Bachelier, inverse, spreads, portfolio MM.

Hosts the math from:

- ``inspiration/notebooks-master/Greeks_under_normal_model.ipynb``
- ``inspiration/notebooks-master/inverse_option.ipynb``
- ``inspiration/stock-analysis-engine-master/analysis_engine/build_option_spread_details.py``
- Lucic & Tse, "Optimal option market making and volatility arbitrage"
  (2024-2026) — implemented in :mod:`aqp.options.portfolio_mm`.

Use sub-modules::

    from aqp.options import normal_model, inverse_options, spreads
    from aqp.options import portfolio_mm, greeks_jax  # optional, needs JAX
"""
from __future__ import annotations

from aqp.options import inverse_options, normal_model, spreads

# Optional JAX-backed surfaces; importable even when JAX is missing because
# both modules degrade to NumPy fallbacks. Listed here so ``aqp.options.*``
# autocomplete works in editors with the ``optimal-control`` extra.
from aqp.options import greeks_jax, portfolio_mm

__all__ = [
    "greeks_jax",
    "inverse_options",
    "normal_model",
    "portfolio_mm",
    "spreads",
]
