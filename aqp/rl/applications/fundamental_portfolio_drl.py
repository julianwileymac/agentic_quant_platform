"""Fundamentals-DRL portfolio allocation with Markowitz post-allocation.

Mirrors the FinRL-Trading pattern from
``inspiration/FinRL-Trading-master/src/strategies/fundamental_portfolio_drl.py``:

1. Pre-select the universe from fundamental rankings (top-N by some
   composite score the caller passes).
2. Train a DRL policy on
   :class:`aqp.rl.envs.portfolio_env.PortfolioAllocationEnv`.
3. After the policy emits softmax weights, apply a Markowitz overlay
   to re-shape the allocation toward minimum-variance (FinRL-Trading
   uses ``EfficientFrontier`` from PyPortfolioOpt; we use the
   in-house :class:`MinVariancePortfolio` so the platform stays
   self-contained).

The application returns a dict with the trained model path + the
final blended weights for the most recent bar.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aqp.config import settings

logger = logging.getLogger(__name__)


def _markowitz_overlay(
    drl_weights: dict[str, float],
    bars: pd.DataFrame,
    *,
    blend: float = 0.5,
    lookback: int = 252,
) -> dict[str, float]:
    """Blend DRL softmax weights with min-variance weights.

    ``blend=0`` returns the pure DRL output, ``blend=1`` returns the
    pure min-variance output. The default 50/50 mirrors the FinRL-Trading
    inspiration's "Markowitz post-allocation" step.
    """
    if not drl_weights:
        return {}
    syms = list(drl_weights.keys())
    sub = bars[bars["vt_symbol"].isin(syms)] if not bars.empty else bars
    if sub.empty:
        return drl_weights
    pivot = sub.pivot_table(
        index="timestamp", columns="vt_symbol", values="close"
    ).sort_index()
    pivot = pivot.tail(int(lookback)).pct_change().dropna()
    if pivot.empty or pivot.shape[1] < 2:
        return drl_weights
    cov = pivot.cov().values
    syms_cov = list(pivot.columns)
    try:
        inv = np.linalg.pinv(cov)
        ones = np.ones(len(syms_cov))
        raw = inv @ ones
        denom = ones @ raw
        if denom == 0:
            mv = np.ones(len(syms_cov)) / len(syms_cov)
        else:
            mv = raw / denom
        mv = np.clip(mv, 0.0, 1.0)
        mv = mv / mv.sum() if mv.sum() > 0 else np.ones(len(syms_cov)) / len(syms_cov)
    except Exception:
        logger.exception("fundamental_drl: min-variance blend failed")
        return drl_weights
    mv_map = dict(zip(syms_cov, mv))
    blended = {}
    for sym in syms:
        drl_w = float(drl_weights.get(sym, 0.0))
        mv_w = float(mv_map.get(sym, 0.0))
        blended[sym] = (1.0 - float(blend)) * drl_w + float(blend) * mv_w
    total = sum(blended.values())
    if total > 0:
        blended = {k: v / total for k, v in blended.items()}
    return blended


def train_fundamental_portfolio_drl(
    symbols: list[str],
    start: str,
    end: str,
    *,
    algo: str = "ppo",
    total_timesteps: int = 150_000,
    initial_balance: float = 100_000.0,
    markowitz_blend: float = 0.5,
    markowitz_lookback: int = 252,
    run_name: str | None = None,
    model_dir: str | Path | None = None,
    feature_set_name: str | None = None,
) -> dict[str, Any]:
    """Train a DRL allocator + return blended Markowitz weights.

    The function is a façade — for richer experiments call the
    underlying :class:`PortfolioAllocationEnv` and ``SB3Adapter``
    directly. Optional ``feature_set_name`` augments the env's
    observation space with the named feature set.
    """
    from aqp.core.types import Symbol
    from aqp.data.duckdb_engine import DuckDBHistoryProvider
    from aqp.rl.agents.sb3_adapter import SB3Adapter
    from aqp.rl.envs.portfolio_env import PortfolioAllocationEnv

    if feature_set_name:
        try:
            from aqp.data.feature_sets import FeatureSetService

            FeatureSetService().record_usage(
                FeatureSetService().get_by_name(feature_set_name).id,  # type: ignore[union-attr]
                consumer_kind="rl",
                consumer_id=run_name,
                meta={"app": "fundamental_portfolio_drl"},
            )
        except Exception:
            logger.info("fundamental_drl: feature_set lookup skipped", exc_info=True)

    env = PortfolioAllocationEnv(
        symbols=symbols,
        start=start,
        end=end,
        initial_balance=initial_balance,
    )
    adapter = SB3Adapter(algo=algo, policy="MlpPolicy")
    adapter.build(env)
    adapter.train(total_timesteps=total_timesteps)

    out_dir = Path(model_dir) if model_dir else (
        settings.models_dir / "rl" / (run_name or f"fundamental-drl-{algo}")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    save_path = out_dir / "model.zip"
    adapter.save(save_path)

    # Generate the most-recent allocation by running one deterministic step.
    blended_weights: dict[str, float] = {}
    try:
        obs = env.reset()
        if isinstance(obs, tuple):
            obs = obs[0]
        action, _ = adapter.policy.predict(obs, deterministic=True)  # type: ignore[union-attr]
        # Action is softmax-shaped; align with env.symbols.
        action = np.asarray(action, dtype=float).reshape(-1)
        if action.size and action.sum() > 0:
            action = action / action.sum()
        if action.size == len(symbols):
            drl_weights = {sym: float(w) for sym, w in zip(symbols, action)}
            provider = DuckDBHistoryProvider()
            bars = provider.get_bars(
                [Symbol.parse(s) for s in symbols],
                start=pd.Timestamp(start),
                end=pd.Timestamp(end),
            )
            blended_weights = _markowitz_overlay(
                drl_weights,
                bars,
                blend=markowitz_blend,
                lookback=markowitz_lookback,
            )
    except Exception:
        logger.exception("fundamental_drl: post-train allocation failed")

    return {
        "symbols": symbols,
        "algo": algo,
        "total_timesteps": total_timesteps,
        "model_path": str(save_path),
        "run_name": run_name or f"fundamental-drl-{algo}",
        "drl_weights": dict(blended_weights),
        "markowitz_blend": float(markowitz_blend),
        "feature_set_name": feature_set_name,
    }


__all__ = ["_markowitz_overlay", "train_fundamental_portfolio_drl"]
