"""Macro / economic time-series standard models."""
from __future__ import annotations

from datetime import date as dateType
from decimal import Decimal

from pydantic import Field

from aqp.core.domain.economic import (
    BlsSeries,
    ConsumerPriceIndex,
    CotReport,
    FederalFundsRate,
    FredObservation,
    FredSeriesMeta,
    GdpNominal,
    GdpReal,
    MoneyMeasures,
    NonFarmPayrolls,
    TreasuryAuction,
    TreasuryPrice,
    TreasuryRate,
    Unemployment,
    YieldCurve,
)
from aqp.providers.base import Data, QueryParams


class _RangeQP(QueryParams):
    start_date: dateType | None = None
    end_date: dateType | None = None


class TreasuryRatesQueryParams(_RangeQP):
    tenor: str | None = None


class TreasuryRatesData(Data, TreasuryRate):
    pass


class TreasuryAuctionsQueryParams(_RangeQP):
    security_type: str | None = None


class TreasuryAuctionsData(Data, TreasuryAuction):
    pass


class TreasuryPricesQueryParams(_RangeQP):
    cusip: str | None = None


class TreasuryPricesData(Data, TreasuryPrice):
    pass


class YieldCurveQueryParams(QueryParams):
    date: dateType | None = None
    country: str | None = None


class YieldCurveData(Data, YieldCurve):
    pass


class FederalFundsRateQueryParams(_RangeQP):
    pass


class FederalFundsRateData(Data, FederalFundsRate):
    pass


class ConsumerPriceIndexQueryParams(_RangeQP):
    country: str | None = None
    category: str | None = None


class ConsumerPriceIndexData(Data, ConsumerPriceIndex):
    pass


class UnemploymentQueryParams(_RangeQP):
    country: str | None = None


class UnemploymentData(Data, Unemployment):
    pass


class NonFarmPayrollsQueryParams(_RangeQP):
    pass


class NonFarmPayrollsData(Data, NonFarmPayrolls):
    pass


class GdpRealQueryParams(_RangeQP):
    country: str | None = None


class GdpRealData(Data, GdpReal):
    pass


class GdpNominalQueryParams(_RangeQP):
    country: str | None = None


class GdpNominalData(Data, GdpNominal):
    pass


class MoneyMeasuresQueryParams(_RangeQP):
    country: str | None = None


class MoneyMeasuresData(Data, MoneyMeasures):
    pass


class FredSeriesQueryParams(QueryParams):
    series_id: str = Field(description="FRED series id (e.g. DGS10).")
    start_date: dateType | None = None
    end_date: dateType | None = None


class FredSeriesData(Data, FredObservation):
    pass


class FredSeriesMetaQueryParams(QueryParams):
    series_id: str


class FredSeriesMetaData(Data, FredSeriesMeta):
    pass


class CotQueryParams(QueryParams):
    commodity: str
    start_date: dateType | None = None
    end_date: dateType | None = None
    report_type: str | None = None


class CotData(Data, CotReport):
    pass


class BlsSeriesQueryParams(QueryParams):
    series_id: str
    start_date: dateType | None = None
    end_date: dateType | None = None


class BlsSeriesData(Data, BlsSeries):
    pass
