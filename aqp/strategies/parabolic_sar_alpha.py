"""Parabolic SAR alpha — trend flips.

Ref: ``inspiration/quant-trading-master/Parabolic SAR backtest.py``.

Uses :class:`aqp.core.indicators.ParabolicSAR` (already in the zoo) —
signals are generated when the SAR flips from above-price to below (long)
or below-price to above (short).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.indicators import ParabolicSAR
from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import BarData, Direction, Signal, Symbol

STRATEGY_TAGS = ("trend", "quant-trading")


@register(
    "ParabolicSARAlpha",
    kind="strategy",
    tags=STRATEGY_TAGS,
    source="quant_trading",
    category="trend",
)
class ParabolicSARAlpha(IAlphaModel):
    def __init__(
        self,
        acceleration: float = 0.02,
        max_acceleration: float = 0.2,
        allow_short: bool = True,
    ) -> None:
        self.acceleration = float(acceleration)
        self.max_acceleration = float(max_acceleration)
        self.allow_short = bool(allow_short)

    def _sar_series(self, sub: pd.DataFrame) -> pd.Series:
        sar = ParabolicSAR(
            af_start=self.acceleration,
            af_step=self.acceleration,
            af_max=self.max_acceleration,
        )
        vals: list[float] = []
        for row in sub.itertuples():
            bar = BarData(
                symbol=Symbol.parse(row.vt_symbol),
                timestamp=row.timestamp,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )
            try:
                vals.append(float(sar.update(bar, row.timestamp)))
            except Exception:
                vals.append(float("nan"))
        return pd.Series(vals, index=sub.index)

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []
        universe_set = {s.vt_symbol for s in universe}
        now = context.get("current_time")
        signals: list[Signal] = []
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            if vt_symbol not in universe_set:
                continue
            sub = sub.sort_values("timestamp")
            if len(sub) < 5:
                continue
            sar = self._sar_series(sub)
            if sar.dropna().empty or len(sar) < 2:
                continue
            close_now = float(sub["close"].iloc[-1])
            close_prev = float(sub["close"].iloc[-2])
            sar_now = float(sar.iloc[-1])
            sar_prev = float(sar.iloc[-2])
            ts = now or sub["timestamp"].iloc[-1]

            flipped_long = sar_prev > close_prev and sar_now < close_now
            flipped_short = sar_prev < close_prev and sar_now > close_now
            if flipped_long:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=0.5,
                        direction=Direction.LONG,
                        timestamp=ts,
                        confidence=0.6,
                        source="ParabolicSARAlpha",
                        rationale=f"SAR flipped below (SAR={sar_now:.2f} < close={close_now:.2f})",
                    )
                )
            elif flipped_short and self.allow_short:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=0.5,
                        direction=Direction.SHORT,
                        timestamp=ts,
                        confidence=0.6,
                        source="ParabolicSARAlpha",
                        rationale=f"SAR flipped above (SAR={sar_now:.2f} > close={close_now:.2f})",
                    )
                )
        return signals
