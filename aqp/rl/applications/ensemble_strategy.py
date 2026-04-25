"""Ensemble RL strategy wrapped as an ``IAlphaModel``.

The training orchestrator (``train_ensemble``) mirrors the FinRL ICAIF
2020 "Ensemble Strategy" notebook: walk-forward train three SB3 models,
pick the best on a validation window, and save the winner.

At inference time the :class:`EnsembleAlpha` loads the saved winner
and produces :class:`Signal` objects in the same way as
:class:`aqp.strategies.rl_policy.RLPolicyAlpha`.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol
from aqp.rl.agents.ensemble import EnsembleAgent, EnsembleMember

logger = logging.getLogger(__name__)


def train_ensemble(
    train_env,
    val_env=None,
    *,
    total_timesteps: int = 100_000,
    validation_steps: int = 1_000,
    save_path: str | Path | None = None,
) -> EnsembleAgent:
    """Train A2C / PPO / DDPG and persist the best.

    Parameters
    ----------
    train_env / val_env:
        Pre-built gymnasium envs. ``val_env`` defaults to ``train_env``
        when not provided (single-window mode).
    total_timesteps:
        Training budget per member.
    validation_steps:
        Steps rolled out in the validation env to score each member.
    save_path:
        If provided, the winner's checkpoint is written under this
        directory as ``best.zip`` and can be loaded with
        :meth:`EnsembleAgent.load`.
    """
    agent = EnsembleAgent(
        members=[
            EnsembleMember(name="a2c", algo="a2c"),
            EnsembleMember(name="ppo", algo="ppo"),
            EnsembleMember(name="ddpg", algo="ddpg"),
        ],
        total_timesteps=total_timesteps,
        validation_steps=validation_steps,
    )
    agent.train(train_env, val_env=val_env)
    if save_path:
        agent.save(save_path)
    return agent


@register("EnsembleAlpha")
class EnsembleAlpha(IAlphaModel):
    """Load a winner from :func:`train_ensemble` and emit signals.

    The alpha doesn't care which base algorithm won; it just loads the
    saved checkpoint via SB3's ``.load`` and evaluates actions.
    """

    def __init__(
        self,
        model_path: str,
        algo: str = "ppo",
        indicators: list[str] | None = None,
        threshold: float = 0.1,
    ) -> None:
        self.model_path = Path(model_path)
        self.algo = algo.lower()
        self.indicators = indicators or ["macd", "rsi_14", "sma_20", "sma_50"]
        self.threshold = float(threshold)
        self._model: Any | None = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from stable_baselines3 import A2C, DDPG, PPO, SAC, TD3  # noqa: F401

            zoo = {"a2c": A2C, "ppo": PPO, "ddpg": DDPG, "sac": SAC, "td3": TD3}
            cls = zoo.get(self.algo)
            if cls is None:
                raise RuntimeError(f"Unsupported ensemble algo: {self.algo}")
            candidate = self.model_path
            if candidate.is_dir():
                candidate = candidate / "best.zip"
            self._model = cls.load(candidate.as_posix())
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load ensemble model from {self.model_path}: {exc}"
            ) from exc

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        self._load()
        if bars.empty or self._model is None:
            return []
        now = context.get("current_time")
        signals: list[Signal] = []
        for sym in universe:
            sub = bars[bars["vt_symbol"] == sym.vt_symbol].sort_values("timestamp")
            if sub.empty:
                continue
            latest = sub.iloc[-1]
            vec: list[float] = [float(latest.get("close", 0.0))]
            vec.extend(float(latest.get(col, 0.0)) for col in self.indicators)
            obs = np.asarray(vec, dtype=np.float32)
            try:
                action, _ = self._model.predict(obs, deterministic=True)
            except Exception:
                continue
            value = float(np.asarray(action).flatten()[0])
            if abs(value) < self.threshold:
                continue
            signals.append(
                Signal(
                    symbol=sym,
                    strength=min(1.0, abs(value)),
                    direction=Direction.LONG if value > 0 else Direction.SHORT,
                    timestamp=now,
                    confidence=0.65,
                    horizon_days=1,
                    source=f"EnsembleAlpha({self.algo})",
                    rationale=f"ensemble action={value:.3f}",
                )
            )
        return signals
