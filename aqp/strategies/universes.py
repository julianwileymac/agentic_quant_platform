"""Universe-selection models (Lean stage 1)."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from aqp.core.interfaces import IUniverseSelectionModel
from aqp.core.registry import register
from aqp.core.types import Exchange, Symbol


@register("StaticUniverse")
class StaticUniverse(IUniverseSelectionModel):
    """Hard-coded list of tickers. The simplest possible universe."""

    def __init__(self, symbols: Iterable[str], exchange: str = Exchange.NASDAQ.value) -> None:
        self.exchange = Exchange(exchange)
        self._symbols = [Symbol(ticker=s, exchange=self.exchange) for s in symbols]

    def select(self, timestamp: datetime, context: dict[str, Any]) -> list[Symbol]:
        return list(self._symbols)


@register("TopVolumeUniverse")
class TopVolumeUniverse(IUniverseSelectionModel):
    """Dynamic: select top-N symbols by trailing 20-day average volume."""

    def __init__(self, n: int = 20, lookback_days: int = 20) -> None:
        self.n = n
        self.lookback_days = lookback_days

    def select(self, timestamp: datetime, context: dict[str, Any]) -> list[Symbol]:
        bars = context.get("bars")
        if bars is None or bars.empty:
            return []
        recent = bars[
            (bars["timestamp"] <= timestamp)
            & (bars["timestamp"] >= timestamp.normalize() - pd.Timedelta(days=self.lookback_days))  # type: ignore
        ]
        ranked = (
            recent.groupby("vt_symbol")["volume"]
            .mean()
            .sort_values(ascending=False)
            .head(self.n)
            .index
        )
        return [Symbol.parse(s) for s in ranked]


# local import kept out of top-level to avoid pandas import on every load
try:  # pragma: no cover
    import pandas as pd  # noqa: F401
except ImportError:  # pragma: no cover
    pass
