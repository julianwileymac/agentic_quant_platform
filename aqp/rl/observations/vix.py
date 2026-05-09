"""VIX observation block — single scalar from ``env_state["vix"]``."""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

import numpy as np

from aqp.rl.core.observation import BaseObservationBuilder


class VIXBuilder(BaseObservationBuilder):
    """Reads the precomputed ``vix`` series (merged by the data pipeline)."""

    rl_alias: ClassVar[str] = "VIXBuilder"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "risk"

    def __init__(self, *, scale: float = 0.01) -> None:
        super().__init__(name="vix")
        self.scale = float(scale)

    @property
    def output_shape(self) -> tuple[int, ...]:
        return (1,)

    def feature_names(self) -> list[str]:
        return ["vix"]

    def build(self, idx: int, env_state: Mapping[str, Any]) -> np.ndarray:
        series = env_state.get("vix")
        if series is None:
            return np.zeros(1, dtype=np.float32)
        try:
            value = float(series.iloc[int(idx)])
        except Exception:  # noqa: BLE001
            value = 0.0
        return np.asarray([value * self.scale], dtype=np.float32)


__all__ = ["VIXBuilder"]
