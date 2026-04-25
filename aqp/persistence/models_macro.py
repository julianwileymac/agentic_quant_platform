"""Macro / economic / market-microstructure persistence tables."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Time,
)

from aqp.persistence.models import Base, _uuid


class EconomicSeriesRow(Base):
    """Generic economic-series master (complements ``fred_series``).

    ``source`` distinguishes FRED / BLS / ECB / OECD / Trading Economics /
    custom. Observations live in ``economic_observations`` keyed by
    ``series_id``.
    """

    __tablename__ = "economic_series"
    id = Column(String(36), primary_key=True, default=_uuid)
    series_id = Column(String(64), nullable=False, index=True)
    source = Column(String(32), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    country = Column(String(64), nullable=True)
    country_iso = Column(String(8), nullable=True)
    frequency = Column(String(32), nullable=True)
    frequency_short = Column(String(8), nullable=True)
    units = Column(String(120), nullable=True)
    units_short = Column(String(60), nullable=True)
    seasonal_adjustment = Column(String(16), nullable=True)
    category = Column(String(120), nullable=True)
    release = Column(String(120), nullable=True)
    notes = Column(Text, nullable=True)
    popularity = Column(Integer, nullable=True)
    observation_start = Column(Date, nullable=True)
    observation_end = Column(Date, nullable=True)
    last_updated = Column(DateTime, nullable=True)
    meta = Column(JSON, default=dict)

    __table_args__ = (
        Index("uq_economic_series_source_id", "source", "series_id", unique=True),
    )


class EconomicObservation(Base):
    __tablename__ = "economic_observations"
    id = Column(String(36), primary_key=True, default=_uuid)
    series_id = Column(String(64), nullable=False, index=True)
    source = Column(String(32), nullable=False, index=True)
    country = Column(String(64), nullable=True)
    date = Column(Date, nullable=False, index=True)
    value = Column(Float, nullable=True)
    prior = Column(Float, nullable=True)
    revised = Column(Float, nullable=True)
    vintage_date = Column(Date, nullable=True)
    release_ts = Column(DateTime, nullable=True)
    unit = Column(String(32), nullable=True)
    provider = Column(String(64), nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("uq_econ_obs", "source", "series_id", "date", "vintage_date", unique=True),
    )


class CotReportRow(Base):
    __tablename__ = "cot_reports"
    id = Column(String(36), primary_key=True, default=_uuid)
    report_type = Column(String(24), nullable=True)
    commodity = Column(String(120), nullable=False, index=True)
    commodity_code = Column(String(32), nullable=True, index=True)
    market = Column(String(120), nullable=True)
    exchange = Column(String(32), nullable=True)
    report_date = Column(Date, nullable=False, index=True)
    open_interest = Column(Float, nullable=True)
    noncommercial_long = Column(Float, nullable=True)
    noncommercial_short = Column(Float, nullable=True)
    noncommercial_spreading = Column(Float, nullable=True)
    commercial_long = Column(Float, nullable=True)
    commercial_short = Column(Float, nullable=True)
    nonreportable_long = Column(Float, nullable=True)
    nonreportable_short = Column(Float, nullable=True)
    trader_count = Column(Integer, nullable=True)
    concentration_4_long = Column(Float, nullable=True)
    concentration_4_short = Column(Float, nullable=True)
    source = Column(String(32), default="CFTC")
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("uq_cot_commodity_date", "commodity_code", "report_date", "report_type", unique=True),
    )


class BlsSeriesRow(Base):
    __tablename__ = "bls_series"
    id = Column(String(36), primary_key=True, default=_uuid)
    series_id = Column(String(64), nullable=False, unique=True, index=True)
    survey = Column(String(120), nullable=True)
    measure_data_type = Column(String(120), nullable=True)
    seasonal_adjustment = Column(String(16), nullable=True)
    title = Column(String(512), nullable=True)
    units = Column(String(120), nullable=True)
    last_updated = Column(DateTime, nullable=True)
    meta = Column(JSON, default=dict)


class TreasuryRateRow(Base):
    __tablename__ = "treasury_rates"
    id = Column(String(36), primary_key=True, default=_uuid)
    date = Column(Date, nullable=False, index=True)
    tenor = Column(String(8), nullable=False, index=True)  # 1m/3m/6m/1y/...
    nominal_rate = Column(Float, nullable=True)
    real_rate = Column(Float, nullable=True)
    is_constant_maturity = Column(Boolean, default=True)
    source = Column(String(32), default="UST")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("uq_treasury_rate", "date", "tenor", unique=True),)


class YieldCurveRow(Base):
    """Daily snapshot of a yield curve — stores the full point set in JSON."""

    __tablename__ = "yield_curves"
    id = Column(String(36), primary_key=True, default=_uuid)
    date = Column(Date, nullable=False, index=True)
    country = Column(String(64), nullable=True, index=True)
    curve_name = Column(String(64), nullable=True)
    points = Column(JSON, default=list)
    source = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("uq_yield_curve", "date", "country", "curve_name", unique=True),
    )


# ---------------------------------------------------------------------------
# Options / futures specifics
# ---------------------------------------------------------------------------


class OptionSeries(Base):
    """A (underlying, expiry) series of options, indexed for fast lookup."""

    __tablename__ = "option_series"
    id = Column(String(36), primary_key=True, default=_uuid)
    underlying = Column(String(64), nullable=False, index=True)
    underlying_instrument_id = Column(
        String(36),
        ForeignKey("instruments.id"),
        nullable=True,
        index=True,
    )
    expiry = Column(Date, nullable=False, index=True)
    contract_count = Column(Integer, nullable=True)
    first_listed = Column(Date, nullable=True)
    last_traded = Column(DateTime, nullable=True)
    meta = Column(JSON, default=dict)

    __table_args__ = (
        Index("uq_option_series", "underlying", "expiry", unique=True),
    )


class OptionChainSnapshot(Base):
    """One saved options-chain snapshot (strikes × kinds + greeks)."""

    __tablename__ = "option_chains_snapshots"
    id = Column(String(36), primary_key=True, default=_uuid)
    underlying = Column(String(64), nullable=False, index=True)
    expiry = Column(Date, nullable=False, index=True)
    snapshot_ts = Column(DateTime, nullable=False, index=True)
    underlying_price = Column(Float, nullable=True)
    provider = Column(String(64), nullable=True)
    payload = Column(JSON, default=list)  # list[OptionChainSlice]
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FuturesCurveRow(Base):
    __tablename__ = "futures_curves"
    id = Column(String(36), primary_key=True, default=_uuid)
    root_symbol = Column(String(32), nullable=False, index=True)
    expiry = Column(Date, nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    price = Column(Float, nullable=False)
    volume = Column(Float, nullable=True)
    open_interest = Column(Float, nullable=True)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("uq_futures_curve", "root_symbol", "expiry", "snapshot_date", unique=True),
    )


# ---------------------------------------------------------------------------
# Market microstructure
# ---------------------------------------------------------------------------


class MarketHolidayRow(Base):
    __tablename__ = "market_holidays"
    id = Column(String(36), primary_key=True, default=_uuid)
    exchange = Column(String(32), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    name = Column(String(240), nullable=True)
    is_half_day = Column(Boolean, default=False)
    close_time = Column(Time, nullable=True)
    open_time = Column(Time, nullable=True)
    is_observed = Column(Boolean, default=True)
    meta = Column(JSON, default=dict)

    __table_args__ = (Index("uq_market_holiday", "exchange", "date", unique=True),)


class MarketStatusHistory(Base):
    __tablename__ = "market_status_history"
    id = Column(String(36), primary_key=True, default=_uuid)
    exchange = Column(String(32), nullable=False, index=True)
    instrument_id = Column(String(36), ForeignKey("instruments.id"), nullable=True, index=True)
    status = Column(String(32), nullable=False, index=True)
    reason = Column(String(240), nullable=True)
    halt_code = Column(String(32), nullable=True)
    ts_event = Column(DateTime, nullable=False, index=True)
    ts_init = Column(DateTime, nullable=True)
    meta = Column(JSON, default=dict)

    __table_args__ = (
        Index("ix_mkt_status_exchange_ts", "exchange", "ts_event"),
    )
