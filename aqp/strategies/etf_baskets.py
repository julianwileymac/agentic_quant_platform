"""Pre-baked ETF-basket universes (Lean-style)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from aqp.core.interfaces import IUniverseSelectionModel
from aqp.core.registry import register
from aqp.core.types import Exchange, Symbol

_LIQUID_ETFS = [
    "SPY", "QQQ", "IWM", "DIA", "VTI", "EEM", "EFA", "IEFA", "GLD", "SLV",
    "USO", "TLT", "AGG", "HYG", "LQD", "XLK", "XLV", "XLF", "XLE", "XLY",
    "XLI", "XLP", "XLRE", "XLB", "XLU",
]

_SECTOR_ETFS = ["XLK", "XLV", "XLF", "XLE", "XLY", "XLI", "XLP", "XLRE", "XLB", "XLU", "XLC"]

_US_TREASURY_ETFS = ["SHY", "IEI", "IEF", "TLT", "TIP", "GOVT", "AGG", "BND"]

_VOLATILITY_ETFS = ["VXX", "VIXY", "UVXY", "SVXY"]


class _StaticBasketUniverse(IUniverseSelectionModel):
    """Return a pre-configured list of tickers on every call."""

    basket: list[str] = []

    def __init__(self, exchange: str = Exchange.NASDAQ.value) -> None:
        self.exchange = Exchange(exchange)

    def select(self, timestamp: datetime, context: dict[str, Any]) -> list[Symbol]:
        return [Symbol(ticker=t, exchange=self.exchange) for t in self.basket]


@register("LiquidETFUniverse")
class LiquidETFUniverse(_StaticBasketUniverse):
    basket = list(_LIQUID_ETFS)


@register("SectorETFUniverse")
class SectorETFUniverse(_StaticBasketUniverse):
    basket = list(_SECTOR_ETFS)


@register("USTreasuriesETFUniverse")
class USTreasuriesETFUniverse(_StaticBasketUniverse):
    basket = list(_US_TREASURY_ETFS)


@register("VolatilityETFUniverse")
class VolatilityETFUniverse(_StaticBasketUniverse):
    basket = list(_VOLATILITY_ETFS)
