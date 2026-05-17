"""RL environments — existing AQP envs + FinRL ports + placeholders.

Importing this package eagerly registers every env class through the
:class:`aqp.rl.core.base.RLComponentMeta` metaclass so the
``GET /rl/components/rl_env`` introspection endpoint and the lab UI
palette can enumerate them without scanning the filesystem.
"""
from __future__ import annotations

from aqp.rl.envs.execution_env import ExecutionEnv
from aqp.rl.envs.finrl_crypto_env import FinRLCryptoEnv
from aqp.rl.envs.finrl_portfolio_cov_env import FinRLPortfolioCovEnv
from aqp.rl.envs.finrl_stock_env import FinRLStockTradingEnv
from aqp.rl.envs.finrl_stock_np_env import FinRLStockTradingNpEnv
from aqp.rl.envs.lucic_tse_options_env import LucicTsePortfolioEnv
from aqp.rl.envs.market_making_env import MarketMakingEnv, MarketMakingStubEnv
from aqp.rl.envs.mbtgym_adapter import MbtGymAdapterEnv
from aqp.rl.envs.optimal_execution_env import OptimalExecutionEnv
from aqp.rl.envs.options_env import OptionsTradingEnv
from aqp.rl.envs.portfolio_env import PortfolioAllocationEnv
from aqp.rl.envs.rl_backtest_env import RLBacktestEnv
from aqp.rl.envs.stock_trading_discrete import StockTradingDiscreteEnv
from aqp.rl.envs.stock_trading_env import StockTradingEnv

__all__ = [
    "ExecutionEnv",
    "FinRLCryptoEnv",
    "FinRLPortfolioCovEnv",
    "FinRLStockTradingEnv",
    "FinRLStockTradingNpEnv",
    "LucicTsePortfolioEnv",
    "MarketMakingEnv",
    "MarketMakingStubEnv",
    "MbtGymAdapterEnv",
    "OptimalExecutionEnv",
    "OptionsTradingEnv",
    "PortfolioAllocationEnv",
    "RLBacktestEnv",
    "StockTradingDiscreteEnv",
    "StockTradingEnv",
]
