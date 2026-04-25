"""Single-stock discrete stock-trading application façade.

Thin wrapper that builds a :class:`StockTradingDiscreteEnv`, trains an
SB3 agent via the existing :func:`aqp.rl.trainer.train_from_config`
entry point, and returns a summary dict.

Mirrors FinRL's ``examples/FinRL_StockTrading_*.py`` so users can go
from "pick a ticker" to "trained policy" in one call without writing
YAML.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)


def train_stock_trading(
    symbol: str,
    start: str,
    end: str,
    *,
    algo: str = "ppo",
    total_timesteps: int = 100_000,
    initial_balance: float = 10_000.0,
    run_name: str | None = None,
    model_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Train a single-stock policy and save the weights."""
    from aqp.rl.agents.sb3_adapter import SB3Adapter
    from aqp.rl.envs.stock_trading_discrete import StockTradingDiscreteEnv

    env = StockTradingDiscreteEnv(
        symbol=symbol,
        start=start,
        end=end,
        initial_balance=initial_balance,
    )
    adapter = SB3Adapter(algo=algo, policy="MlpPolicy")
    adapter.build(env)
    adapter.train(total_timesteps=total_timesteps)

    out_dir = Path(model_dir) if model_dir else (settings.models_dir / "rl" / (run_name or f"{symbol}-{algo}"))
    out_dir.mkdir(parents=True, exist_ok=True)
    save_path = out_dir / "model.zip"
    adapter.save(save_path)

    return {
        "symbol": symbol,
        "algo": algo,
        "total_timesteps": total_timesteps,
        "model_path": str(save_path),
        "run_name": run_name or f"{symbol}-{algo}",
    }
