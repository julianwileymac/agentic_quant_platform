"""Oil-money regression alpha — FX residual mean-reversion.

Ref: ``inspiration/quant-trading-master/Oil Money project/Oil Money Trading backtest.py``.

Fits a rolling OLS regression of a petrocurrency FX rate (``target``) on a
crude oil proxy (``regressor``). When the rolling R² is high and the
residual of the latest bar exceeds ``k`` rolling-σ, we fade it: long the
petrocurrency when its residual is deep negative (FX is cheap vs oil
implies), short when strongly positive.

Usage note: this alpha expects *both* symbols to be present in the bars
frame; it filters by ``target_symbol`` / ``regressor_symbol`` kwargs.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

STRATEGY_TAGS = ("statistical", "mean-reversion", "quant-trading")


@register("OilMoneyRegressionAlpha")
class OilMoneyRegressionAlpha(IAlphaModel):
    def __init__(
        self,
        target_symbol: str,
        regressor_symbol: str,
        lookback: int = 60,
        z_threshold: float = 2.0,
        min_rsquare: float = 0.4,
        allow_short: bool = True,
    ) -> None:
        self.target_symbol = str(target_symbol)
        self.regressor_symbol = str(regressor_symbol)
        self.lookback = int(lookback)
        self.z_threshold = float(z_threshold)
        self.min_rsquare = float(min_rsquare)
        self.allow_short = bool(allow_short)

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []
        now = context.get("current_time")
        target = bars[bars["vt_symbol"] == self.target_symbol].sort_values("timestamp")
        regressor = bars[bars["vt_symbol"] == self.regressor_symbol].sort_values("timestamp")
        if len(target) < self.lookback + 1 or len(regressor) < self.lookback + 1:
            return []
        merged = target[["timestamp", "close"]].merge(
            regressor[["timestamp", "close"]],
            on="timestamp",
            suffixes=("_tgt", "_reg"),
        )
        if len(merged) < self.lookback + 1:
            return []
        window = merged.tail(self.lookback)
        x = window["close_reg"].values
        y = window["close_tgt"].values
        xm = x.mean()
        ym = y.mean()
        denom = ((x - xm) ** 2).sum()
        if denom == 0:
            return []
        slope = ((x - xm) * (y - ym)).sum() / denom
        intercept = ym - slope * xm
        resid = y - (slope * x + intercept)
        sigma = resid.std(ddof=0)
        if sigma == 0:
            return []
        pred = slope * merged["close_reg"].iloc[-1] + intercept
        actual = merged["close_tgt"].iloc[-1]
        z = float((actual - pred) / sigma)
        r2 = (((slope * x + intercept) - ym) ** 2).sum() / (((y - ym) ** 2).sum() + 1e-12)
        ts = now or merged["timestamp"].iloc[-1]

        if r2 < self.min_rsquare:
            return []
        if z <= -self.z_threshold:
            return [
                Signal(
                    symbol=Symbol.parse(self.target_symbol),
                    strength=float(min(1.0, abs(z) / self.z_threshold - 1.0 + 0.5)),
                    direction=Direction.LONG,
                    timestamp=ts,
                    confidence=float(min(1.0, r2)),
                    source="OilMoneyRegressionAlpha",
                    rationale=f"resid z={z:.2f} (R²={r2:.2f})",
                )
            ]
        if z >= self.z_threshold and self.allow_short:
            return [
                Signal(
                    symbol=Symbol.parse(self.target_symbol),
                    strength=float(min(1.0, abs(z) / self.z_threshold - 1.0 + 0.5)),
                    direction=Direction.SHORT,
                    timestamp=ts,
                    confidence=float(min(1.0, r2)),
                    source="OilMoneyRegressionAlpha",
                    rationale=f"resid z={z:.2f} (R²={r2:.2f})",
                )
            ]
        return []
