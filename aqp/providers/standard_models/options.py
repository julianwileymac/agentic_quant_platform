"""Options chains, snapshots, unusual activity."""
from __future__ import annotations

from datetime import date as dateType, datetime
from decimal import Decimal

from pydantic import Field, field_validator

from aqp.providers.base import Data, QueryParams


class OptionsChainsQueryParams(QueryParams):
    symbol: str
    expiry: dateType | None = None
    strike_min: Decimal | None = None
    strike_max: Decimal | None = None

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return v.upper() if isinstance(v, str) else v


class OptionsChainsData(Data):
    underlying_symbol: str | None = None
    contract_symbol: str | None = None
    expiry: dateType | None = None
    strike: Decimal
    option_type: str  # call/put
    bid: Decimal | None = None
    ask: Decimal | None = None
    last_price: Decimal | None = None
    volume: Decimal | None = None
    open_interest: Decimal | None = None
    implied_volatility: Decimal | None = None
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    rho: Decimal | None = None
    dte: int | None = None
    in_the_money: bool | None = None


class OptionsSnapshotsQueryParams(QueryParams):
    symbol: str | None = None
    date: dateType | None = None


class OptionsSnapshotsData(Data):
    timestamp: datetime
    underlying: str
    contract_symbol: str
    strike: Decimal
    expiry: dateType
    option_type: str
    bid: Decimal | None = None
    ask: Decimal | None = None
    last_price: Decimal | None = None
    volume: Decimal | None = None
    open_interest: Decimal | None = None


class OptionsUnusualQueryParams(QueryParams):
    symbol: str | None = None
    date: dateType | None = None
    option_type: str | None = None
    volume_min: Decimal | None = None


class OptionsUnusualData(Data):
    timestamp: datetime
    underlying: str
    contract_symbol: str
    strike: Decimal
    expiry: dateType
    option_type: str
    premium: Decimal | None = None
    volume: Decimal | None = None
    open_interest: Decimal | None = None
    volume_oi_ratio: Decimal | None = None
    side: str | None = None  # buy | sell
    trade_count: int | None = None
