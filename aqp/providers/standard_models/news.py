"""News standard models."""
from __future__ import annotations

from datetime import date as dateType, datetime

from pydantic import Field, field_validator

from aqp.core.domain.news import CompanyNews, WorldNews
from aqp.providers.base import Data, QueryParams


def _upper(v: str | None) -> str | None:
    return v.upper() if isinstance(v, str) else v


class CompanyNewsQueryParams(QueryParams):
    symbols: str = Field(description="Comma-separated tickers.")
    start_date: dateType | None = None
    end_date: dateType | None = None
    limit: int | None = 50

    @field_validator("symbols", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class CompanyNewsData(Data, CompanyNews):
    pass


class WorldNewsQueryParams(QueryParams):
    start_date: dateType | None = None
    end_date: dateType | None = None
    limit: int | None = 50
    country: str | None = None
    topic: str | None = None


class WorldNewsData(Data, WorldNews):
    pass
