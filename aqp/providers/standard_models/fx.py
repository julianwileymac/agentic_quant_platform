"""FX currency-pair reference + historical prices + reference rates."""
from __future__ import annotations

from datetime import date as dateType, datetime
from decimal import Decimal

from pydantic import Field

from aqp.providers.base import Data, QueryParams


class CurrencyPairsQueryParams(QueryParams):
    query: str | None = None


class CurrencyPairsData(Data):
    symbol: str
    base_currency: str | None = None
    quote_currency: str | None = None
    name: str | None = None
    category: str | None = None
    venue: str | None = None


class CurrencyHistoricalQueryParams(QueryParams):
    symbol: str
    start_date: dateType | None = None
    end_date: dateType | None = None
    interval: str = "1d"


class CurrencyHistoricalData(Data):
    date: dateType | datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class CurrencyReferenceRatesQueryParams(QueryParams):
    base_currency: str = "USD"
    quote_currencies: str | None = None
    date: dateType | None = None


class CurrencyReferenceRatesData(Data):
    date: dateType
    base: str
    quote: str
    rate: Decimal


class CurrencySnapshotsQueryParams(QueryParams):
    base: str = "USD"


class CurrencySnapshotsData(Data):
    symbol: str
    base: str | None = None
    quote: str | None = None
    rate: Decimal
    change: Decimal | None = None
    change_pct: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    last_updated: datetime | None = None
