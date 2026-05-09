"""Microstructure observation bridge to :mod:`aqp.data.microstructure`.

Reads pre-computed microstructure features (spread, order-flow imbalance,
volume-clock metrics) into the observation vector.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

import numpy as np

from aqp.rl.core.observation import BaseObservationBuilder


_DEFAULT_COLUMNS: tuple[str, ...] = (
    "spread_bps",
    "order_flow_imbalance",
    "vol_clock",
)


class MicrostructureBuilder(BaseObservationBuilder):
    """Per-asset microstructure feature block."""

    rl_alias: ClassVar[str] = "MicrostructureBuilder"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "microstructure"

    DEFAULT_COLUMNS: ClassVar[tuple[str, ...]] = _DEFAULT_COLUMNS

    def __init__(
        self,
        *,
        n_assets: int,
        columns: list[str] | None = None,
    ) -> None:
        super().__init__(name="microstructure")
        self.n_assets = int(n_assets)
        self.columns = list(columns or self.DEFAULT_COLUMNS)

    @property
    def output_shape(self) -> tuple[int, ...]:
        return (self.n_assets * len(self.columns),)

    def feature_names(self) -> list[str]:
        return [f"{col}_{i}" for col in self.columns for i in range(self.n_assets)]

    def build(self, idx: int, env_state: Mapping[str, Any]) -> np.ndarray:
        feature_tables = env_state.get("feature_tables") or {}
        parts: list[np.ndarray] = []
        for col in self.columns:
            table = feature_tables.get(col)
            if table is None:
                parts.append(np.zeros(self.n_assets, dtype=np.float32))
                continue
            try:
                row = table.iloc[int(idx)].values
            except Exception:  # noqa: BLE001
                row = np.zeros(self.n_assets, dtype=np.float32)
            arr = np.asarray(row, dtype=np.float32).flatten()
            if arr.size < self.n_assets:
                arr = np.pad(arr, (0, self.n_assets - arr.size))
            elif arr.size > self.n_assets:
                arr = arr[: self.n_assets]
            parts.append(arr)
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


__all__ = ["MicrostructureBuilder"]
