"""Bond reference, prices, trades, indices."""
from __future__ import annotations

from datetime import date as dateType
from decimal import Decimal

from pydantic import Field

from aqp.providers.base import Data, QueryParams


class BondReferenceQueryParams(QueryParams):
    cusip: str | None = None
    isin: str | None = None
    issuer: str | None = None


class BondReferenceData(Data):
    cusip: str | None = None
    isin: str | None = None
    issuer: str | None = None
    coupon: Decimal | None = None
    coupon_frequency: str | None = None
    issue_date: dateType | None = None
    maturity_date: dateType | None = None
    face_value: Decimal | None = None
    currency: str | None = None
    day_count: str | None = None
    seniority: str | None = None
    rating_sp: str | None = None
    rating_moodys: str | None = None
    rating_fitch: str | None = None
    callable: bool | None = None
    putable: bool | None = None
    convertible: bool | None = None
    country: str | None = None


class BondPricesQueryParams(QueryParams):
    cusip: str | None = None
    isin: str | None = None
    date: dateType | None = None


class BondPricesData(Data):
    cusip: str | None = None
    date: dateType
    price: Decimal | None = None
    yield_to_maturity: Decimal | None = None
    yield_to_worst: Decimal | None = None
    duration: Decimal | None = None
    modified_duration: Decimal | None = None


class BondTradesQueryParams(QueryParams):
    cusip: str | None = None
    isin: str | None = None
    date: dateType | None = None


class BondTradesData(Data):
    cusip: str | None = None
    trade_date: dateType
    quantity: Decimal | None = None
    price: Decimal | None = None
    yield_pct: Decimal | None = None


class BondIndicesQueryParams(QueryParams):
    index: str
    start_date: dateType | None = None
    end_date: dateType | None = None


class BondIndicesData(Data):
    date: dateType
    index: str
    yield_pct: Decimal | None = None
    oas: Decimal | None = None
    spread_bps: Decimal | None = None
