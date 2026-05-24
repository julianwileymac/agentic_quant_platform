"""RL environments — existing AQP envs + FinRL ports + placeholders.

Importing this package eagerly registers every env class through the
:class:`aqp_rl.core.base.RLComponentMeta` metaclass so the
``GET /rl/components/rl_env`` introspection endpoint and the lab UI
palette can enumerate them without scanning the filesystem.
"""
from __future__ import annotations

from aqp_rl.envs.execution_env import ExecutionEnv
from aqp_rl.envs.finrl_crypto_env import FinRLCryptoEnv
from aqp_rl.envs.finrl_portfolio_cov_env import FinRLPortfolioCovEnv
from aqp_rl.envs.finrl_stock_env import FinRLStockTradingEnv
from aqp_rl.envs.finrl_stock_np_env import FinRLStockTradingNpEnv
from aqp_rl.envs.lucic_tse_options_env import LucicTsePortfolioEnv
from aqp_rl.envs.market_making_env import MarketMakingEnv, MarketMakingStubEnv
from aqp_rl.envs.mbtgym_adapter import MbtGymAdapterEnv
from aqp_rl.envs.optimal_execution_env import OptimalExecutionEnv
from aqp_rl.envs.options_env import OptionsTradingEnv
from aqp_rl.envs.portfolio_env import PortfolioAllocationEnv
from aqp_rl.envs.rl_backtest_env import RLBacktestEnv
from aqp_rl.envs.stock_trading_discrete import StockTradingDiscreteEnv
from aqp_rl.envs.stock_trading_env import StockTradingEnv

# TradeMaster-inspired ``tradesim_*`` envs (Phase 3 of the production-
# enhancement plan). Each ports a TradeMaster domain env into AQP's
# :class:`BaseRLEnv` / metaclass conventions with the Gymnasium 5-tuple
# step contract + a BaseDataset-friendly data path.
from aqp_rl.envs.tradesim_algotrading import AlgorithmicTradingEnv
from aqp_rl.envs.tradesim_execution import OrderExecutionEnv
from aqp_rl.envs.tradesim_hft import HighFrequencyTradingEnv
from aqp_rl.envs.tradesim_multimodal import MultimodalTradingEnv
from aqp_rl.envs.tradesim_portfolio import PortfolioManagementEnv

__all__ = [
    "AlgorithmicTradingEnv",
    "ExecutionEnv",
    "FinRLCryptoEnv",
    "FinRLPortfolioCovEnv",
    "FinRLStockTradingEnv",
    "FinRLStockTradingNpEnv",
    "HighFrequencyTradingEnv",
    "LucicTsePortfolioEnv",
    "MarketMakingEnv",
    "MarketMakingStubEnv",
    "MbtGymAdapterEnv",
    "MultimodalTradingEnv",
    "OptimalExecutionEnv",
    "OptionsTradingEnv",
    "OrderExecutionEnv",
    "PortfolioAllocationEnv",
    "PortfolioManagementEnv",
    "RLBacktestEnv",
    "StockTradingDiscreteEnv",
    "StockTradingEnv",
]
