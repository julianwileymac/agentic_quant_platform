"""ETF reference, pricing, holdings, sector/country breakdown."""
from __future__ import annotations

from datetime import date as dateType, datetime
from decimal import Decimal

from pydantic import Field, field_validator

from aqp.providers.base import Data, QueryParams


def _upper(v: str | None) -> str | None:
    return v.upper() if isinstance(v, str) else v


class EtfInfoQueryParams(QueryParams):
    symbol: str

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class EtfInfoData(Data):
    symbol: str
    name: str | None = None
    description: str | None = None
    inception_date: dateType | None = None
    issuer: str | None = None
    category: str | None = None
    asset_class: str | None = None
    expense_ratio: Decimal | None = None
    aum: Decimal | None = None
    nav: Decimal | None = None
    holdings_count: int | None = None
    underlying_index: str | None = None
    benchmark: str | None = None
    is_leveraged: bool | None = None
    leverage: Decimal | None = None
    is_inverse: bool | None = None
    replication_method: str | None = None
    country: str | None = None
    currency: str | None = None


class EtfHistoricalQueryParams(QueryParams):
    symbol: str
    start_date: dateType | None = None
    end_date: dateType | None = None
    interval: str = "1d"


class EtfHistoricalData(Data):
    date: dateType | datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | int | None = None
    vwap: float | None = None


class EtfHistoricalNavQueryParams(QueryParams):
    symbol: str
    start_date: dateType | None = None
    end_date: dateType | None = None


class EtfHistoricalNavData(Data):
    date: dateType
    symbol: str
    nav: Decimal
    market_price: Decimal | None = None
    premium_discount_pct: Decimal | None = None


class EtfHoldingsQueryParams(QueryParams):
    symbol: str
    date: dateType | None = None
    limit: int | None = None


class EtfHoldingsData(Data):
    symbol: str | None = None
    name: str | None = None
    cusip: str | None = None
    isin: str | None = None
    asset_class: str | None = None
    sector: str | None = None
    country: str | None = None
    weight: Decimal | None = None
    shares_held: Decimal | None = None
    market_value: Decimal | None = None
    holding_date: dateType | None = None


class EtfSectorsQueryParams(QueryParams):
    symbol: str


class EtfSectorsData(Data):
    sector: str
    weight: Decimal | None = None
    benchmark_weight: Decimal | None = None
    active_weight: Decimal | None = None


class EtfCountriesQueryParams(QueryParams):
    symbol: str


class EtfCountriesData(Data):
    country: str
    country_iso: str | None = None
    weight: Decimal | None = None


class EtfSearchQueryParams(QueryParams):
    query: str | None = None
    category: str | None = None
    issuer: str | None = None


class EtfSearchData(Data):
    symbol: str
    name: str | None = None
    issuer: str | None = None
    category: str | None = None
    asset_class: str | None = None
