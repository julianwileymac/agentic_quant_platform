"""FinRL / FinRobot-inspired application skeletons.

Thin façades over :class:`aqp_rl.runtime.RLRuntime` so users get one
entry point per use-case without having to wire YAML from scratch every
time:

- :mod:`aqp_rl.applications.stock_trading` — single-stock discrete env training.
- :mod:`aqp_rl.applications.portfolio_allocation` — multi-symbol continuous allocation.
- :mod:`aqp_rl.applications.cryptocurrency_trading` — crypto multi-asset env (FinRL port).
- :mod:`aqp_rl.applications.imitation_learning` — BC / GAIL entry points.
- :mod:`aqp_rl.applications.ensemble_strategy` — FinRL ensemble alpha.
- :mod:`aqp_rl.applications.fundamental_portfolio_drl` — FinRL-Trading fundamentals + Markowitz overlay.
- :mod:`aqp_rl.applications.papertrading_finrl` — Alpaca paper-trading bridge for trained RL policies.
"""
from __future__ import annotations

from aqp_rl.applications.cryptocurrency_trading import train_crypto_trading
from aqp_rl.applications.ensemble_strategy import EnsembleAlpha, train_ensemble
from aqp_rl.applications.fundamental_portfolio_drl import train_fundamental_portfolio_drl
from aqp_rl.applications.imitation_learning import (
    train_behavior_cloning,
    train_gail,
    train_imitation,
)
from aqp_rl.applications.papertrading_finrl import paper_trade_finrl
from aqp_rl.applications.portfolio_allocation import train_portfolio_allocation
from aqp_rl.applications.stock_trading import train_stock_trading

__all__ = [
    "EnsembleAlpha",
    "paper_trade_finrl",
    "train_behavior_cloning",
    "train_crypto_trading",
    "train_ensemble",
    "train_fundamental_portfolio_drl",
    "train_gail",
    "train_imitation",
    "train_portfolio_allocation",
    "train_stock_trading",
]
