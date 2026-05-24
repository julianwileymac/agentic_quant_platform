"""``TechnicalIndicatorBuilder`` — port of FinRL's ``stockstats`` block.

Reads pre-computed indicator panels from the env's ``feature_tables``
attribute (FinRL convention: ``feature_tables[indicator] = wide df by
vt_symbol``). Falls back to zeros when an indicator is missing so envs
can be constructed with arbitrary indicator lists.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

import numpy as np

from aqp_rl.core.observation import BaseObservationBuilder


_FINRL_INDICATORS: tuple[str, ...] = (
    "macd",
    "boll_ub",
    "boll_lb",
    "rsi_30",
    "cci_30",
    "dx_30",
    "close_30_sma",
    "close_60_sma",
)


class TechnicalIndicatorBuilder(BaseObservationBuilder):
    """Per-asset technical-indicator block.

    Output is the row-major flatten of ``[indicators × n_assets]``: one
    block per indicator, then concatenated. Matches FinRL's
    ``state[1+stock_dim*2 : 1+stock_dim*(2+len(indicators))]`` layout.
    """

    rl_alias: ClassVar[str] = "TechnicalIndicatorBuilder"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "technical"

    DEFAULT_INDICATORS: ClassVar[tuple[str, ...]] = _FINRL_INDICATORS

    def __init__(
        self,
        *,
        n_assets: int,
        indicators: list[str] | None = None,
    ) -> None:
        super().__init__(name="technical")
        self.n_assets = int(n_assets)
        self.indicators = list(indicators or self.DEFAULT_INDICATORS)

    @property
    def output_shape(self) -> tuple[int, ...]:
        return (self.n_assets * len(self.indicators),)

    def feature_names(self) -> list[str]:
        names: list[str] = []
        for ind in self.indicators:
            for i in range(self.n_assets):
                names.append(f"{ind}_{i}")
        return names

    def build(self, idx: int, env_state: Mapping[str, Any]) -> np.ndarray:
        feature_tables = env_state.get("feature_tables") or {}
        parts: list[np.ndarray] = []
        for name in self.indicators:
            table = feature_tables.get(name)
            if table is None:
                parts.append(np.zeros(self.n_assets, dtype=np.float32))
                continue
            try:
                row = table.iloc[idx].values
            except Exception:  # noqa: BLE001
                row = np.zeros(self.n_assets, dtype=np.float32)
            arr = np.asarray(row, dtype=np.float32).flatten()
            if arr.size < self.n_assets:
                arr = np.pad(arr, (0, self.n_assets - arr.size))
            elif arr.size > self.n_assets:
                arr = arr[: self.n_assets]
            parts.append(arr)
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


__all__ = ["TechnicalIndicatorBuilder"]
