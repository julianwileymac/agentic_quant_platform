"""Futures reference, curve, historical prices, instrument listing."""
from __future__ import annotations

from datetime import date as dateType, datetime
from decimal import Decimal

from pydantic import Field

from aqp.providers.base import Data, QueryParams


class FuturesInfoQueryParams(QueryParams):
    symbol: str


class FuturesInfoData(Data):
    symbol: str
    name: str | None = None
    underlying: str | None = None
    expiry: dateType | None = None
    contract_size: Decimal | None = None
    tick_size: Decimal | None = None
    multiplier: Decimal | None = None
    settlement_type: str | None = None
    exchange: str | None = None
    product_code: str | None = None
    currency: str | None = None


class FuturesCurveQueryParams(QueryParams):
    symbol: str
    date: dateType | None = None


class FuturesCurveData(Data):
    symbol: str
    expiry: dateType
    price: Decimal
    volume: Decimal | None = None
    open_interest: Decimal | None = None


class FuturesHistoricalQueryParams(QueryParams):
    symbol: str
    start_date: dateType | None = None
    end_date: dateType | None = None
    interval: str = "1d"


class FuturesHistoricalData(Data):
    date: dateType | datetime
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float
    volume: float | None = None
    open_interest: float | None = None


class FuturesInstrumentsQueryParams(QueryParams):
    product_code: str | None = None
    exchange: str | None = None


class FuturesInstrumentsData(Data):
    symbol: str
    product_code: str | None = None
    name: str | None = None
    exchange: str | None = None
    expiry: dateType | None = None
    contract_size: Decimal | None = None
