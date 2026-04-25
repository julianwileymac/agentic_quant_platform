"""FinRL-inspired application skeletons.

Thin façades over the existing :mod:`aqp.rl.trainer` / :mod:`aqp.rl.evaluator`
pipeline so users get one entry point per use-case without having to
wire YAML from scratch every time:

- :mod:`aqp.rl.applications.stock_trading` — single-stock discrete env
  training.
- :mod:`aqp.rl.applications.portfolio_allocation` — multi-symbol
  continuous allocation.
- :mod:`aqp.rl.applications.cryptocurrency_trading` — crypto env
  (placeholder until users supply a crypto data source).
- :mod:`aqp.rl.applications.imitation_learning` — BC / GAIL entry
  points that require the ``[finrl-apps]`` optional group.
- :mod:`aqp.rl.applications.ensemble_strategy` — FinRL ensemble alpha.
"""
from __future__ import annotations

from aqp.rl.applications.ensemble_strategy import EnsembleAlpha, train_ensemble
from aqp.rl.applications.portfolio_allocation import train_portfolio_allocation
from aqp.rl.applications.stock_trading import train_stock_trading

__all__ = [
    "EnsembleAlpha",
    "train_ensemble",
    "train_portfolio_allocation",
    "train_stock_trading",
]
