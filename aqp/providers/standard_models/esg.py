"""ESG + sector performance standard models."""
from __future__ import annotations

from datetime import date as dateType
from decimal import Decimal

from pydantic import Field, field_validator

from aqp.providers.base import Data, QueryParams


class EsgScoreQueryParams(QueryParams):
    symbol: str

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return v.upper() if isinstance(v, str) else v


class EsgScoreData(Data):
    symbol: str
    date: dateType | None = None
    overall_score: Decimal | None = None
    environmental_score: Decimal | None = None
    social_score: Decimal | None = None
    governance_score: Decimal | None = None
    controversy_level: int | None = None
    provider: str | None = None


class EsgRiskRatingQueryParams(QueryParams):
    symbol: str


class EsgRiskRatingData(Data):
    symbol: str
    rating: str | None = None
    rating_numeric: Decimal | None = None
    risk_category: str | None = None
    controversy_level: int | None = None
    peer_group: str | None = None
    date: dateType | None = None


class SectorPerformanceQueryParams(QueryParams):
    date: dateType | None = None


class SectorPerformanceData(Data):
    sector: str
    performance_1d: Decimal | None = None
    performance_5d: Decimal | None = None
    performance_1m: Decimal | None = None
    performance_ytd: Decimal | None = None
    performance_1y: Decimal | None = None
    performance_3y: Decimal | None = None
    performance_5y: Decimal | None = None
