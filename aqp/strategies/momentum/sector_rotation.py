"""Sector momentum rotation with top-decile + SMA filter.

Implements the canonical recipe from Kakushadze 2016 (and reproduced
in the 2026 research report): rank sector ETFs by their 6-12-month
formation return, go long the top decile, and gate every allocation
behind a long-term SMA filter on the broad market so the strategy
sits in cash when the market is in a downtrend.
"""
from __future__ import annotations

from typing import Any, Sequence

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol


@register(
    "SectorMomentumRotationAlpha",
    source="research_report_2026",
    category="momentum",
    kind="strategy",
)
class SectorMomentumRotationAlpha(IAlphaModel):
    """Top-decile sector momentum rotation.

    Parameters
    ----------
    formation_period
        Lookback bars (typically months) used to compute momentum.
    top_decile
        Fraction (0..1) of the universe to go long. Default 0.1 = top
        decile per the original recipe; for small universes the
        implementation rounds up to at least one position.
    market_proxy
        Vt symbol of the broad-market trend gauge (e.g. ``SPY.NYSE``).
    market_sma_window
        Bars used for the absolute-trend SMA filter on ``market_proxy``.
        Allocations are suppressed when ``market_proxy`` is below this
        SMA.
    hold_bars
        Forecast horizon attached to each Signal.
    """

    def __init__(
        self,
        formation_period: int = 126,
        top_decile: float = 0.1,
        market_proxy: str | None = "SPY.NYSE",
        market_sma_window: int = 200,
        hold_bars: int = 21,
    ) -> None:
        self.formation_period = int(formation_period)
        self.top_decile = float(top_decile)
        self.market_proxy = market_proxy
        self.market_sma_window = int(market_sma_window)
        self.hold_bars = int(hold_bars)

    def _market_trend_ok(self, bars: pd.DataFrame) -> bool:
        if not self.market_proxy:
            return True
        proxy = bars[bars["vt_symbol"] == self.market_proxy].sort_values("timestamp")
        if proxy.empty:
            return True
        if len(proxy) < self.market_sma_window:
            return True
        close = proxy["close"]
        sma = close.rolling(self.market_sma_window).mean().iloc[-1]
        return bool(close.iloc[-1] >= sma)

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: Sequence[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []
        if not self._market_trend_ok(bars):
            return []
        universe_set = {s.vt_symbol for s in universe}
        rows: list[dict[str, Any]] = []
        now = context.get("current_time")
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            if vt_symbol not in universe_set:
                continue
            sub = sub.sort_values("timestamp")
            if len(sub) < self.formation_period + 1:
                continue
            close = sub["close"]
            momentum = (close.iloc[-1] / close.iloc[-self.formation_period] - 1.0)
            rows.append(
                {
                    "vt_symbol": vt_symbol,
                    "momentum": float(momentum),
                    "ts": sub["timestamp"].iloc[-1],
                }
            )
        if not rows:
            return []
        df = pd.DataFrame(rows).sort_values("momentum", ascending=False)
        n = max(1, int(round(len(df) * self.top_decile)))
        winners = df.head(n)
        signals: list[Signal] = []
        per_weight = 1.0 / float(len(winners))
        for row in winners.itertuples():
            signals.append(
                Signal(
                    symbol=Symbol.parse(row.vt_symbol),
                    strength=float(per_weight),
                    direction=Direction.LONG,
                    timestamp=now or row.ts,
                    confidence=float(min(max(row.momentum, 0.0) * 10.0, 1.0)),
                    horizon_days=self.hold_bars,
                    source="SectorMomentumRotationAlpha",
                    rationale=(
                        f"top-decile momentum={row.momentum:.3f} over "
                        f"{self.formation_period} bars"
                    ),
                )
            )
        return signals
