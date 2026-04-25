"""Crypto historical prices + search."""
from __future__ import annotations

from datetime import date as dateType, datetime

from pydantic import Field

from aqp.providers.base import Data, QueryParams


class CryptoHistoricalQueryParams(QueryParams):
    symbol: str
    start_date: dateType | None = None
    end_date: dateType | None = None
    interval: str = "1d"


class CryptoHistoricalData(Data):
    date: dateType | datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    vwap: float | None = None


class CryptoSearchQueryParams(QueryParams):
    query: str | None = None


class CryptoSearchData(Data):
    symbol: str
    name: str | None = None
    venue: str | None = None
    is_native: bool | None = None
    chain: str | None = None
