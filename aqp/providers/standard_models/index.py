"""Index reference, constituents, snapshots, and search."""
from __future__ import annotations

from datetime import date as dateType, datetime
from decimal import Decimal

from pydantic import Field

from aqp.providers.base import Data, QueryParams


class IndexInfoQueryParams(QueryParams):
    symbol: str


class IndexInfoData(Data):
    symbol: str
    name: str | None = None
    administrator: str | None = None
    methodology: str | None = None
    base_date: dateType | None = None
    constituent_count: int | None = None
    region: str | None = None
    country: str | None = None
    asset_class: str | None = None


class IndexHistoricalQueryParams(QueryParams):
    symbol: str
    start_date: dateType | None = None
    end_date: dateType | None = None
    interval: str = "1d"


class IndexHistoricalData(Data):
    date: dateType | datetime
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float
    volume: float | None = None


class IndexConstituentsQueryParams(QueryParams):
    symbol: str
    date: dateType | None = None


class IndexConstituentsData(Data):
    symbol: str
    name: str | None = None
    weight: Decimal | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    market_cap: Decimal | None = None


class IndexSearchQueryParams(QueryParams):
    query: str | None = None
    region: str | None = None


class IndexSearchData(Data):
    symbol: str
    name: str | None = None
    administrator: str | None = None


class IndexSectorsQueryParams(QueryParams):
    symbol: str


class IndexSectorsData(Data):
    sector: str
    weight: Decimal | None = None
    market_cap: Decimal | None = None
