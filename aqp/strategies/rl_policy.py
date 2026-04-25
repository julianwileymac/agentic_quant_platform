"""Wraps a trained RL policy as a plain ``IAlphaModel`` so it plugs into the
Lean-style 5-stage framework exactly like a hand-coded alpha."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol


@register("RLPolicyAlpha")
class RLPolicyAlpha(IAlphaModel):
    """Load an SB3 policy checkpoint and produce signals from model actions."""

    def __init__(self, model_path: str, indicators: list[str] | None = None) -> None:
        self.model_path = Path(model_path)
        self.indicators = indicators or ["macd", "rsi_14", "sma_20", "sma_50"]
        self._model: Any | None = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from stable_baselines3 import PPO

            self._model = PPO.load(self.model_path.as_posix())
        except Exception:
            try:
                from stable_baselines3 import SAC

                self._model = SAC.load(self.model_path.as_posix())
            except Exception as e:  # pragma: no cover
                raise RuntimeError(
                    f"Failed to load RL policy from {self.model_path}: {e}"
                ) from e

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        self._load()
        if bars.empty:
            return []
        now = context.get("current_time")
        obs_rows: list[np.ndarray] = []
        symbols: list[Symbol] = []
        for sym in universe:
            sub = bars[bars["vt_symbol"] == sym.vt_symbol].sort_values("timestamp")
            if sub.empty:
                continue
            latest = sub.iloc[-1]
            vec = [latest.get("close", 0.0)]
            vec.extend(float(latest.get(col, 0.0)) for col in self.indicators)
            obs_rows.append(np.asarray(vec, dtype=np.float32))
            symbols.append(sym)

        if not symbols:
            return []

        signals: list[Signal] = []
        for sym, obs in zip(symbols, obs_rows, strict=False):
            try:
                action, _ = self._model.predict(obs, deterministic=True)  # type: ignore[union-attr]
            except Exception:
                continue
            value = float(np.asarray(action).flatten()[0])
            if abs(value) < 0.05:
                continue
            signals.append(
                Signal(
                    symbol=sym,
                    strength=min(1.0, abs(value)),
                    direction=Direction.LONG if value > 0 else Direction.SHORT,
                    timestamp=now,
                    confidence=0.6,
                    horizon_days=1,
                    source=f"RLPolicyAlpha({self.model_path.name})",
                    rationale=f"policy action={value:.3f}",
                )
            )
        return signals
