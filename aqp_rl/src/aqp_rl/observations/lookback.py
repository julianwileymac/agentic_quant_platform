"""Lookback-stack observation block — FinRL crypto-env layout.

Stacks the last ``lookback`` rows of one or more feature tables into a
flat vector, matching FinRL's ``CryptoEnv.get_state`` shape.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

import numpy as np

from aqp_rl.core.observation import BaseObservationBuilder


class LookbackStackBuilder(BaseObservationBuilder):
    """``[features × lookback]`` window flatten for fast envs."""

    rl_alias: ClassVar[str] = "LookbackStackBuilder"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "lookback"

    def __init__(
        self,
        *,
        n_assets: int,
        feature_columns: list[str],
        lookback: int = 5,
        scale: float = 1.0,
    ) -> None:
        super().__init__(name="lookback_stack")
        self.n_assets = int(n_assets)
        self.feature_columns = list(feature_columns)
        self.lookback = int(lookback)
        self.scale = float(scale)

    @property
    def output_shape(self) -> tuple[int, ...]:
        return (self.n_assets * len(self.feature_columns) * self.lookback,)

    def feature_names(self) -> list[str]:
        names: list[str] = []
        for lag in range(self.lookback):
            for col in self.feature_columns:
                for i in range(self.n_assets):
                    names.append(f"{col}_lag{lag}_{i}")
        return names

    def build(self, idx: int, env_state: Mapping[str, Any]) -> np.ndarray:
        feature_tables = env_state.get("feature_tables") or {}
        per_lag: list[np.ndarray] = []
        for lag in range(self.lookback):
            t = max(0, int(idx) - lag)
            row_parts: list[np.ndarray] = []
            for col in self.feature_columns:
                table = feature_tables.get(col)
                if table is None:
                    row_parts.append(np.zeros(self.n_assets, dtype=np.float32))
                    continue
                try:
                    row = table.iloc[t].values
                except Exception:  # noqa: BLE001
                    row = np.zeros(self.n_assets, dtype=np.float32)
                arr = np.asarray(row, dtype=np.float32).flatten()
                if arr.size < self.n_assets:
                    arr = np.pad(arr, (0, self.n_assets - arr.size))
                elif arr.size > self.n_assets:
                    arr = arr[: self.n_assets]
                row_parts.append(arr)
            per_lag.append(np.concatenate(row_parts) if row_parts else np.zeros(0, dtype=np.float32))
        flat = np.concatenate(per_lag) if per_lag else np.zeros(0, dtype=np.float32)
        return (flat * self.scale).astype(np.float32, copy=False)


__all__ = ["LookbackStackBuilder"]
