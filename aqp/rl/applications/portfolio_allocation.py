"""Multi-symbol portfolio allocation application façade.

Wraps :class:`aqp.rl.envs.portfolio_env.PortfolioAllocationEnv` +
:class:`aqp.rl.agents.sb3_adapter.SB3Adapter` so users can train a
softmax allocator with one call.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)


def train_portfolio_allocation(
    symbols: list[str],
    start: str,
    end: str,
    *,
    algo: str = "ppo",
    total_timesteps: int = 150_000,
    initial_balance: float = 100_000.0,
    run_name: str | None = None,
    model_dir: str | Path | None = None,
) -> dict[str, Any]:
    from aqp.rl.agents.sb3_adapter import SB3Adapter
    from aqp.rl.envs.portfolio_env import PortfolioAllocationEnv

    env = PortfolioAllocationEnv(
        symbols=symbols,
        start=start,
        end=end,
        initial_balance=initial_balance,
    )
    adapter = SB3Adapter(algo=algo, policy="MlpPolicy")
    adapter.build(env)
    adapter.train(total_timesteps=total_timesteps)

    out_dir = Path(model_dir) if model_dir else (settings.models_dir / "rl" / (run_name or f"portfolio-{algo}"))
    out_dir.mkdir(parents=True, exist_ok=True)
    save_path = out_dir / "model.zip"
    adapter.save(save_path)

    return {
        "symbols": symbols,
        "algo": algo,
        "total_timesteps": total_timesteps,
        "model_path": str(save_path),
        "run_name": run_name or f"portfolio-{algo}",
    }
