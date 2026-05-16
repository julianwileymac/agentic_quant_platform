"""Smoothed moving-average crossover alpha.

Applies an exponential low-pass smoother to the close-price series
before computing the fast/slow MA crossover. The smoothing is meant
to suppress the whipsaws that plague raw MA crossovers in choppy
markets — empirically it raises hit rate at the cost of slight
signal lag.

Reference: research report 2026 (the "Moving Average with smoothing"
trend variant).
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol


def _ema_smoother(series: pd.Series, alpha: float) -> pd.Series:
    """Exponential moving average smoother with `alpha = 2/(N+1)` semantics."""
    return series.ewm(alpha=alpha, adjust=False).mean()


@register(
    "SmoothedMACrossoverAlpha",
    source="research_report_2026",
    category="trend",
    kind="strategy",
)
class SmoothedMACrossoverAlpha(IAlphaModel):
    """Low-pass-smoothed MA crossover.

    Parameters
    ----------
    fast_window
        Fast MA window (bars).
    slow_window
        Slow MA window (bars). Must exceed ``fast_window``.
    smooth_alpha
        EMA smoother strength applied to raw close before the MA
        computation. ``1.0`` disables smoothing; sensible values are
        in ``[0.1, 0.5]``.
    threshold
        Minimum |fast - slow| spread required to emit a signal.
    hold_bars
        Forecast horizon attached to each Signal.
    """

    def __init__(
        self,
        fast_window: int = 20,
        slow_window: int = 50,
        smooth_alpha: float = 0.3,
        threshold: float = 0.0,
        hold_bars: int = 5,
    ) -> None:
        if slow_window <= fast_window:
            raise ValueError("slow_window must exceed fast_window")
        if not 0.0 < smooth_alpha <= 1.0:
            raise ValueError("smooth_alpha must lie in (0, 1]")
        self.fast_window = int(fast_window)
        self.slow_window = int(slow_window)
        self.smooth_alpha = float(smooth_alpha)
        self.threshold = float(threshold)
        self.hold_bars = int(hold_bars)

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: Sequence[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []
        universe_set = {s.vt_symbol for s in universe}
        signals: list[Signal] = []
        now = context.get("current_time")
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            if vt_symbol not in universe_set:
                continue
            sub = sub.sort_values("timestamp")
            if len(sub) < self.slow_window + 1:
                continue
            close = sub["close"].astype(float)
            smoothed = (
                _ema_smoother(close, self.smooth_alpha)
                if self.smooth_alpha < 1.0
                else close
            )
            fast = smoothed.rolling(self.fast_window).mean()
            slow = smoothed.rolling(self.slow_window).mean()
            spread = fast.iloc[-1] - slow.iloc[-1]
            if np.isnan(spread):
                continue
            if abs(spread) < self.threshold:
                continue
            direction = Direction.LONG if spread > 0 else Direction.SHORT
            signals.append(
                Signal(
                    symbol=Symbol.parse(vt_symbol),
                    strength=float(min(abs(spread) / max(float(slow.iloc[-1]), 1e-9), 1.0)),
                    direction=direction,
                    timestamp=now or sub["timestamp"].iloc[-1],
                    confidence=float(min(abs(spread) / max(float(slow.iloc[-1]), 1e-9) * 10.0, 1.0)),
                    horizon_days=self.hold_bars,
                    source="SmoothedMACrossoverAlpha",
                    rationale=(
                        f"fast={fast.iloc[-1]:.4f} slow={slow.iloc[-1]:.4f} "
                        f"spread={spread:.4f} smoothed_alpha={self.smooth_alpha:.2f}"
                    ),
                )
            )
        return signals
