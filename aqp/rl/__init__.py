"""RL-Ops — FinRL-style envs + SB3 adapter + MLflow-tracked trainer."""

import contextlib as _contextlib

from aqp.rl.agents.sb3_adapter import SB3Adapter
from aqp.rl.envs.portfolio_env import PortfolioAllocationEnv
from aqp.rl.envs.stock_trading_env import StockTradingEnv
from aqp.rl.evaluator import evaluate_policy
from aqp.rl.trainer import train_from_config

# Apply paradigm + algo_family tags to existing RL agents and envs at
# import time so the Strategy Browser, Taxonomy Explorer, and
# ``list_by_tag`` surface them without per-class decorator changes.
with _contextlib.suppress(Exception):
    from aqp.rl.tagging import apply_tags as _apply_rl_tags

    _apply_rl_tags()

__all__ = [
    "PortfolioAllocationEnv",
    "SB3Adapter",
    "StockTradingEnv",
    "evaluate_policy",
    "train_from_config",
]
