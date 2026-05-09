"""Cryptocurrency trading façade.

Ports FinRL's ``CryptoEnv`` flow into the AQP runtime by:

1. Building a data pipeline (Iceberg by default) that ingests bars for
   the crypto basket.
2. Constructing :class:`aqp.rl.envs.finrl_crypto_env.FinRLCryptoEnv`
   from the resulting numpy arrays.
3. Driving training through :class:`aqp.rl.runtime.RLRuntime`.

For users who only want bars from a single ticker the function still
falls back gracefully to
:func:`aqp.rl.applications.stock_trading.train_stock_trading` when the
``finrl-crypto`` env can't be constructed.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def train_crypto_trading(
    symbols: list[str] | str,
    start: str,
    end: str,
    *,
    algo: str = "ppo",
    total_timesteps: int = 100_000,
    initial_capital: float = 100_000.0,
    indicators: list[str] | None = None,
    lookback: int = 5,
    run_name: str | None = None,
    model_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Train a DRL crypto allocator on the FinRL multi-crypto env."""
    if isinstance(symbols, str):
        symbols = [symbols]
    indicators = list(indicators or ["macd", "rsi_14", "sma_20"])

    from aqp.config import settings
    from aqp.rl.agents.sb3_adapter import SB3Adapter
    from aqp.rl.data_pipelines.iceberg import IcebergRLDataPipeline
    from aqp.rl.envs.finrl_crypto_env import FinRLCryptoEnv

    try:
        pipeline = IcebergRLDataPipeline(indicators=indicators, use_turbulence=False)
        bundle = pipeline.run_full(
            ticker_list=symbols,
            start=start,
            end=end,
            tech_indicator_list=indicators,
            use_vix=False,
            use_turbulence=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("crypto data pipeline failed; falling back to stock_trading flow")
        from aqp.rl.applications.stock_trading import train_stock_trading

        return train_stock_trading(
            symbol=symbols[0],
            start=start,
            end=end,
            algo=algo,
            total_timesteps=total_timesteps,
            initial_balance=initial_capital,
            run_name=run_name,
            model_dir=model_dir,
        )

    env = FinRLCryptoEnv(
        price_array=bundle.price_array,
        tech_array=bundle.tech_array,
        lookback=lookback,
        initial_capital=initial_capital,
    )
    adapter = SB3Adapter(algorithm=algo, policy="MlpPolicy")
    adapter.build(env)
    adapter.train(total_timesteps=int(total_timesteps))

    out_dir = Path(model_dir) if model_dir else (
        Path(settings.models_dir) / "rl" / (run_name or f"crypto-{algo}")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    save_path = out_dir / "model.zip"
    adapter.save(save_path)
    return {
        "symbols": symbols,
        "algo": algo,
        "total_timesteps": total_timesteps,
        "model_path": str(save_path),
        "run_name": run_name or f"crypto-{algo}",
    }


__all__ = ["train_crypto_trading"]
