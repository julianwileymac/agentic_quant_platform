"""Dual-momentum strategy (Antonacci 2014 / research report 2026).

Combines cross-sectional momentum (relative momentum) with
time-series momentum (absolute momentum). The strategy:

1. Picks the asset with the highest formation-period return.
2. Compares that asset's return against ``cash_proxy`` (e.g. T-Bills /
   TLT).
3. If the chosen asset's return exceeds the cash-proxy return, goes
   long the asset; otherwise allocates to the cash proxy / safe haven.

The safe-haven check is what makes this "dual" — pure relative
momentum can still allocate during a broad market drawdown, while
dual momentum bails out to bonds / cash.
"""
from __future__ import annotations

from typing import Any, Sequence

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol


@register(
    "DualMomentumAlpha",
    source="research_report_2026",
    category="momentum",
    kind="strategy",
)
class DualMomentumAlpha(IAlphaModel):
    """Top-asset selection with absolute-momentum safe-haven escape.

    Parameters
    ----------
    formation_period
        Lookback bars to compute momentum.
    cash_proxy
        Vt symbol of the safe-haven (e.g. ``TLT.NASDAQ``,
        ``IEF.NASDAQ``). Used both for the absolute-momentum compare
        and as the allocation when the market trend is negative.
    hold_bars
        Forecast horizon attached to each Signal.
    """

    def __init__(
        self,
        formation_period: int = 126,
        cash_proxy: str = "TLT.NASDAQ",
        hold_bars: int = 21,
    ) -> None:
        self.formation_period = int(formation_period)
        self.cash_proxy = cash_proxy
        self.hold_bars = int(hold_bars)

    def _trailing_return(self, sub: pd.DataFrame) -> float | None:
        if len(sub) < self.formation_period + 1:
            return None
        close = sub["close"]
        return float(close.iloc[-1] / close.iloc[-self.formation_period] - 1.0)

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: Sequence[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []
        universe_set = {s.vt_symbol for s in universe}
        # Compute trailing returns per symbol, including the cash proxy.
        rows: list[dict[str, Any]] = []
        cash_return: float | None = None
        cash_ts = None
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            sub = sub.sort_values("timestamp")
            trailing = self._trailing_return(sub)
            if trailing is None:
                continue
            if vt_symbol == self.cash_proxy:
                cash_return = trailing
                cash_ts = sub["timestamp"].iloc[-1]
                continue
            if vt_symbol not in universe_set:
                continue
            rows.append(
                {
                    "vt_symbol": vt_symbol,
                    "return": trailing,
                    "ts": sub["timestamp"].iloc[-1],
                }
            )
        if not rows:
            return []
        df = pd.DataFrame(rows).sort_values("return", ascending=False)
        best = df.iloc[0]
        now = context.get("current_time")

        # Absolute-momentum check: if best asset's trailing return is
        # below the cash proxy's, allocate to cash instead.
        if cash_return is not None and best["return"] < cash_return:
            return [
                Signal(
                    symbol=Symbol.parse(self.cash_proxy),
                    strength=1.0,
                    direction=Direction.LONG,
                    timestamp=now or cash_ts,
                    confidence=0.5,
                    horizon_days=self.hold_bars,
                    source="DualMomentumAlpha",
                    rationale=(
                        f"safe haven: top return {best['return']:.3f} < cash "
                        f"{cash_return:.3f}"
                    ),
                )
            ]
        return [
            Signal(
                symbol=Symbol.parse(best["vt_symbol"]),
                strength=1.0,
                direction=Direction.LONG,
                timestamp=now or best["ts"],
                confidence=float(min(max(best["return"], 0.0) * 5.0, 1.0)),
                horizon_days=self.hold_bars,
                source="DualMomentumAlpha",
                rationale=(
                    f"best relative momentum={best['return']:.3f} > cash "
                    f"{cash_return if cash_return is not None else 'n/a'}"
                ),
            )
        ]
