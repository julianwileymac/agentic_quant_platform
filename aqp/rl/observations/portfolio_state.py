"""Portfolio-state observation block — cash + weights / positions.

Default first stack used by every env: ``[cash_ratio, w_1, ..., w_n]``
(or ``[cash, position_value, price]`` for single-asset envs).
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

import numpy as np

from aqp.rl.core.observation import BaseObservationBuilder


class PortfolioStateBuilder(BaseObservationBuilder):
    """Cash + weights/positions block."""

    rl_alias: ClassVar[str] = "PortfolioStateBuilder"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "portfolio"

    def __init__(self, *, n_assets: int, include_cash: bool = True, normalise_by_balance: bool = True) -> None:
        super().__init__(name="portfolio_state")
        self.n_assets = int(n_assets)
        self.include_cash = bool(include_cash)
        self.normalise_by_balance = bool(normalise_by_balance)

    @property
    def output_shape(self) -> tuple[int, ...]:
        return ((1 if self.include_cash else 0) + self.n_assets,)

    def feature_names(self) -> list[str]:
        names: list[str] = []
        if self.include_cash:
            names.append("cash_ratio")
        names.extend([f"weight_{i}" for i in range(self.n_assets)])
        return names

    def build(self, idx: int, env_state: Mapping[str, Any]) -> np.ndarray:
        weights = env_state.get("weights")
        if weights is None:
            weights = np.zeros(self.n_assets, dtype=np.float32)
        weights = np.asarray(weights, dtype=np.float32).flatten()
        if weights.size < self.n_assets:
            weights = np.pad(weights, (0, self.n_assets - weights.size))
        elif weights.size > self.n_assets:
            weights = weights[: self.n_assets]
        out: list[np.ndarray] = []
        if self.include_cash:
            pv = float(env_state.get("portfolio_value", 0.0) or 0.0)
            invested = float(np.sum(weights * pv))
            cash_ratio = (pv - invested) / max(pv, 1e-9)
            if not self.normalise_by_balance:
                cash_ratio = pv - invested
            out.append(np.asarray([cash_ratio], dtype=np.float32))
        out.append(weights.astype(np.float32, copy=False))
        return np.concatenate(out)


__all__ = ["PortfolioStateBuilder"]
