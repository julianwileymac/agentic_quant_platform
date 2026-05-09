"""Covariance-matrix observation block (FinRL ``StockPortfolioEnv``).

Computes a rolling covariance matrix from the env's price panel and
flattens it into the observation vector.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

import numpy as np

from aqp.rl.core.observation import BaseObservationBuilder


class CovarianceBuilder(BaseObservationBuilder):
    """Rolling-window per-step covariance matrix flatten.

    Mirrors FinRL's ``StockPortfolioEnv``: at step ``idx`` it pulls the
    last ``lookback`` rows from ``env_state["price_panel"]`` (a wide
    DataFrame indexed by timestamp, columns ``vt_symbol``) and emits the
    flattened covariance matrix.
    """

    rl_alias: ClassVar[str] = "CovarianceBuilder"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "risk"

    def __init__(self, *, n_assets: int, lookback: int = 60) -> None:
        super().__init__(name="covariance")
        self.n_assets = int(n_assets)
        self.lookback = int(lookback)

    @property
    def output_shape(self) -> tuple[int, ...]:
        return (self.n_assets * self.n_assets,)

    def feature_names(self) -> list[str]:
        return [f"cov_{i}_{j}" for i in range(self.n_assets) for j in range(self.n_assets)]

    def build(self, idx: int, env_state: Mapping[str, Any]) -> np.ndarray:
        panel = env_state.get("price_panel")
        if panel is None:
            return np.zeros(self.n_assets * self.n_assets, dtype=np.float32)
        try:
            window_start = max(0, int(idx) - self.lookback)
            window = panel.iloc[window_start : int(idx) + 1]
            if len(window) < 2:
                return np.zeros(self.n_assets * self.n_assets, dtype=np.float32)
            returns = window.pct_change().dropna()
            cov = returns.cov().values
        except Exception:  # noqa: BLE001
            return np.zeros(self.n_assets * self.n_assets, dtype=np.float32)
        flat = np.asarray(cov, dtype=np.float32).flatten()
        if flat.size != self.n_assets * self.n_assets:
            out = np.zeros(self.n_assets * self.n_assets, dtype=np.float32)
            out[: min(flat.size, out.size)] = flat[: min(flat.size, out.size)]
            return out
        return flat


__all__ = ["CovarianceBuilder"]
