"""Fundamental / liquidity-based universe selection (Lean-style)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from aqp.core.interfaces import IUniverseSelectionModel
from aqp.core.registry import register
from aqp.core.types import Exchange, Symbol


@register("FundamentalUniverse")
class FundamentalUniverse(IUniverseSelectionModel):
    """Rank-and-cut universe by dollar volume or market cap.

    ``sort_by`` options:
    - ``"dollar_volume"`` — mean ``close × volume`` over ``lookback_days``.
    - ``"volume"`` — mean bar volume over ``lookback_days``.

    Pulls bars from ``context["bars"]`` (the backtest engine places the
    full history there); during paper sessions the live feed's rolling
    window fills the same slot.
    """

    def __init__(
        self,
        top_n: int = 100,
        sort_by: str = "dollar_volume",
        lookback_days: int = 20,
        exchange: str = Exchange.NASDAQ.value,
    ) -> None:
        self.top_n = int(top_n)
        self.sort_by = sort_by
        self.lookback_days = int(lookback_days)
        self.exchange = Exchange(exchange)

    def select(self, timestamp: datetime, context: dict[str, Any]) -> list[Symbol]:
        bars: pd.DataFrame = context.get("bars") or context.get("history") or pd.DataFrame()
        if bars.empty:
            return []
        cutoff = pd.Timestamp(timestamp) - pd.Timedelta(days=self.lookback_days)
        recent = bars[bars["timestamp"] >= cutoff]
        if recent.empty:
            return []
        if self.sort_by == "dollar_volume":
            score = (recent["close"] * recent["volume"]).groupby(recent["vt_symbol"]).mean()
        elif self.sort_by == "volume":
            score = recent.groupby("vt_symbol")["volume"].mean()
        else:
            raise ValueError(f"unknown sort_by: {self.sort_by!r}")
        top = score.sort_values(ascending=False).head(self.top_n).index.tolist()
        out: list[Symbol] = []
        for vt in top:
            try:
                out.append(Symbol.parse(vt))
            except Exception:
                out.append(Symbol(ticker=vt.split(".")[0], exchange=self.exchange))
        return out
