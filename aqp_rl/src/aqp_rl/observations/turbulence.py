"""Turbulence index observation block.

Two flavours:

- Reads the precomputed ``turbulence`` series from
  ``env_state["turbulence"]`` (FinRL convention — populated by the data
  pipeline's ``add_turbulence``).
- Falls back to a Mahalanobis-style port of FinRL's
  ``calculate_turbulence`` over ``env_state["price_panel"]`` if no
  precomputed series is available.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

import numpy as np

from aqp_rl.core.observation import BaseObservationBuilder


class TurbulenceBuilder(BaseObservationBuilder):
    """Single-scalar turbulence index, scaled."""

    rl_alias: ClassVar[str] = "TurbulenceBuilder"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "risk"

    def __init__(self, *, lookback: int = 252, scale: float = 1.0 / 100.0) -> None:
        super().__init__(name="turbulence")
        self.lookback = int(lookback)
        self.scale = float(scale)

    @property
    def output_shape(self) -> tuple[int, ...]:
        return (1,)

    def feature_names(self) -> list[str]:
        return ["turbulence"]

    def build(self, idx: int, env_state: Mapping[str, Any]) -> np.ndarray:
        # Fast path: precomputed series.
        series = env_state.get("turbulence")
        if series is not None:
            try:
                value = float(series.iloc[int(idx)])
            except Exception:  # noqa: BLE001
                value = 0.0
            return np.asarray([value * self.scale], dtype=np.float32)
        # Fallback: rolling Mahalanobis on price panel.
        panel = env_state.get("price_panel")
        if panel is None or int(idx) < self.lookback:
            return np.zeros(1, dtype=np.float32)
        try:
            window = panel.iloc[max(0, int(idx) - self.lookback) : int(idx) + 1]
            returns = window.pct_change().dropna()
            if len(returns) < 2:
                return np.zeros(1, dtype=np.float32)
            cov = returns.cov().values
            current = returns.iloc[-1].values - returns.mean(axis=0).values
            inv = np.linalg.pinv(cov)
            value = float(current @ inv @ current)
        except Exception:  # noqa: BLE001
            value = 0.0
        return np.asarray([value * self.scale], dtype=np.float32)


__all__ = ["TurbulenceBuilder"]
