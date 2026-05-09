"""``FundamentalBuilder`` — bridge to FinRobot-style fundamentals.

Reads a fundamentals panel (``DataFrame`` indexed by ``date`` × ``tic``)
from ``env_state["fundamentals"]`` and emits a per-asset feature block.
The panel is expected to be already aligned to the env's bar index by
the data pipeline (typically
:class:`aqp.rl.data_pipelines.iceberg.IcebergRLDataPipeline`).
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

import numpy as np

from aqp.rl.core.observation import BaseObservationBuilder

DEFAULT_COLUMNS: tuple[str, ...] = (
    "pe_ratio",
    "pb_ratio",
    "debt_to_equity",
    "roa",
    "roe",
    "ebitda_margin",
)


class FundamentalBuilder(BaseObservationBuilder):
    """Per-asset fundamental feature block."""

    rl_alias: ClassVar[str] = "FundamentalBuilder"
    rl_source: ClassVar[str] = "finrobot"
    rl_category: ClassVar[str] = "fundamentals"

    DEFAULT_COLUMNS: ClassVar[tuple[str, ...]] = DEFAULT_COLUMNS

    def __init__(
        self,
        *,
        n_assets: int,
        columns: list[str] | None = None,
        scale: float = 1.0,
    ) -> None:
        super().__init__(name="fundamentals")
        self.n_assets = int(n_assets)
        self.columns = list(columns or self.DEFAULT_COLUMNS)
        self.scale = float(scale)

    @property
    def output_shape(self) -> tuple[int, ...]:
        return (self.n_assets * len(self.columns),)

    def feature_names(self) -> list[str]:
        return [f"{col}_{i}" for col in self.columns for i in range(self.n_assets)]

    def build(self, idx: int, env_state: Mapping[str, Any]) -> np.ndarray:
        panel = env_state.get("fundamentals")
        if panel is None:
            return np.zeros(self.n_assets * len(self.columns), dtype=np.float32)
        parts: list[np.ndarray] = []
        for col in self.columns:
            try:
                row = panel[col].iloc[int(idx)] if hasattr(panel, "iloc") else panel.get(col)
                arr = np.asarray(row, dtype=np.float32).flatten()
            except Exception:  # noqa: BLE001
                arr = np.zeros(self.n_assets, dtype=np.float32)
            if arr.size < self.n_assets:
                arr = np.pad(arr, (0, self.n_assets - arr.size))
            elif arr.size > self.n_assets:
                arr = arr[: self.n_assets]
            parts.append(arr)
        return (np.concatenate(parts) * self.scale).astype(np.float32, copy=False)


__all__ = ["FundamentalBuilder"]
