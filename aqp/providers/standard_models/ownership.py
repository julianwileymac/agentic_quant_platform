"""Ownership standard models."""
from __future__ import annotations

from datetime import date as dateType, datetime
from decimal import Decimal

from pydantic import Field, field_validator

from aqp.core.domain.ownership import (
    EquityFtd as _EquityFtd,
    EquityOwnershipSnapshot,
    EquityPeerGroup,
    Form13FHolding,
    GovernmentTrade,
    InsiderTransaction,
    InstitutionalHolding,
    SharesFloat,
    ShortInterest,
    TopRetail,
)
from aqp.providers.base import Data, QueryParams


def _upper(v: str | None) -> str | None:
    return v.upper() if isinstance(v, str) else v


class InsiderTradingQueryParams(QueryParams):
    symbol: str
    limit: int | None = None

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class InsiderTradingData(Data, InsiderTransaction):
    pass


class InstitutionalOwnershipQueryParams(QueryParams):
    symbol: str
    date: dateType | None = None
    limit: int | None = None

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class InstitutionalOwnershipData(Data, InstitutionalHolding):
    pass


class Form13FhrQueryParams(QueryParams):
    cik: str | None = None
    date: dateType | None = None


class Form13FhrData(Data, Form13FHolding):
    pass


class KeyExecutivesQueryParams(QueryParams):
    symbol: str

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class KeyExecutivesData(Data):
    symbol: str | None = None
    name: str
    title: str | None = None
    tenure_start: dateType | None = None
    age: int | None = None
    gender: str | None = None
    compensation: Decimal | None = None
    compensation_currency: str | None = None
    fiscal_year: int | None = None


class ExecutiveCompensationQueryParams(QueryParams):
    symbol: str

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class ExecutiveCompensationData(Data):
    symbol: str | None = None
    executive_name: str
    title: str | None = None
    fiscal_year: int | None = None
    salary: Decimal | None = None
    bonus: Decimal | None = None
    stock_awards: Decimal | None = None
    option_awards: Decimal | None = None
    non_equity_incentives: Decimal | None = None
    pension: Decimal | None = None
    other_compensation: Decimal | None = None
    total: Decimal | None = None
    currency: str | None = "USD"


class EquityPeersQueryParams(QueryParams):
    symbol: str

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class EquityPeersData(Data, EquityPeerGroup):
    pass


class EquityOwnershipQueryParams(QueryParams):
    symbol: str
    date: dateType | None = None

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class EquityOwnershipData(Data, EquityOwnershipSnapshot):
    pass


class EquityShortInterestQueryParams(QueryParams):
    symbol: str

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class EquityShortInterestData(Data, ShortInterest):
    pass


class ShortVolumeQueryParams(QueryParams):
    symbol: str
    start_date: dateType | None = None
    end_date: dateType | None = None


class ShortVolumeData(Data):
    symbol: str
    date: dateType
    short_volume: Decimal | None = None
    short_exempt_volume: Decimal | None = None
    total_volume: Decimal | None = None
    short_volume_pct: Decimal | None = None


class EquityFtdQueryParams(QueryParams):
    symbol: str | None = None
    start_date: dateType | None = None
    end_date: dateType | None = None


class EquityFtdData(Data, _EquityFtd):
    pass


class GovernmentTradesQueryParams(QueryParams):
    symbol: str | None = None
    chamber: str | None = None
    start_date: dateType | None = None
    end_date: dateType | None = None


class GovernmentTradesData(Data, GovernmentTrade):
    pass


class TopRetailQueryParams(QueryParams):
    limit: int | None = 50


class TopRetailData(Data, TopRetail):
    pass
