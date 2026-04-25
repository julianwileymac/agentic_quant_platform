"""Event + calendar persistence tables.

- ``corporate_events`` — polymorphic (split/dividend/spinoff/merger/ipo/…).
- ``earnings_events`` / ``dividend_events`` / ``split_events`` / ``ipo_events``
  / ``merger_events`` — dedicated event tables with type-specific fields.
- ``calendar_events`` — polymorphic upcoming-event calendar.
- ``analyst_estimates``, ``price_targets``, ``forward_estimates``.
- ``regulatory_events``, ``esg_events``.
"""
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
)

from aqp.persistence.models import Base, _uuid


class CorporateEvent(Base):
    """Canonical corporate-action event record.

    ``kind`` discriminates split / dividend / spinoff / merger / delisting /
    rename / buyback / ipo / secondary / rights_issue / bankruptcy / …
    """

    __tablename__ = "corporate_events"
    id = Column(String(36), primary_key=True, default=_uuid)
    kind = Column(String(32), nullable=False, index=True)
    instrument_id = Column(String(36), ForeignKey("instruments.id"), nullable=True, index=True)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    vt_symbol = Column(String(64), nullable=True, index=True)

    ex_date = Column(Date, nullable=True, index=True)
    record_date = Column(Date, nullable=True)
    pay_date = Column(Date, nullable=True)
    declaration_date = Column(Date, nullable=True)
    announcement_text = Column(Text, nullable=True)

    value = Column(Float, nullable=True)
    ratio = Column(Float, nullable=True)
    currency = Column(String(16), nullable=True)
    new_symbol = Column(String(64), nullable=True)

    source = Column(String(64), nullable=True)
    source_filing_accession = Column(String(32), nullable=True, index=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_corp_event_instrument_kind", "instrument_id", "kind"),
        Index("ix_corp_event_ex_date", "ex_date"),
    )


class EarningsEventRow(Base):
    __tablename__ = "earnings_events"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    fiscal_period = Column(String(16), nullable=True)
    fiscal_year = Column(Integer, nullable=True)
    announcement_ts = Column(DateTime, nullable=True, index=True)
    call_start_ts = Column(DateTime, nullable=True)
    eps_estimate = Column(Float, nullable=True)
    eps_actual = Column(Float, nullable=True)
    eps_surprise = Column(Float, nullable=True)
    eps_surprise_pct = Column(Float, nullable=True)
    revenue_estimate = Column(Float, nullable=True)
    revenue_actual = Column(Float, nullable=True)
    revenue_surprise = Column(Float, nullable=True)
    transcript_id = Column(String(36), ForeignKey("earnings_call_transcripts.id"), nullable=True)
    source = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index(
            "uq_earnings_event",
            "issuer_id",
            "fiscal_year",
            "fiscal_period",
            unique=True,
        ),
    )


class DividendEventRow(Base):
    __tablename__ = "dividend_events"
    id = Column(String(36), primary_key=True, default=_uuid)
    instrument_id = Column(String(36), ForeignKey("instruments.id"), nullable=True, index=True)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(16), default="USD")
    ex_date = Column(Date, nullable=True, index=True)
    record_date = Column(Date, nullable=True)
    pay_date = Column(Date, nullable=True)
    declaration_date = Column(Date, nullable=True)
    frequency = Column(String(32), nullable=True)
    is_special = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SplitEventRow(Base):
    __tablename__ = "split_events"
    id = Column(String(36), primary_key=True, default=_uuid)
    instrument_id = Column(String(36), ForeignKey("instruments.id"), nullable=True, index=True)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    numerator = Column(Float, nullable=True)
    denominator = Column(Float, nullable=True)
    ratio = Column(String(32), nullable=True)
    ex_date = Column(Date, nullable=True, index=True)
    record_date = Column(Date, nullable=True)
    pay_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class IpoEventRow(Base):
    __tablename__ = "ipo_events"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    pricing_date = Column(Date, nullable=True)
    listing_date = Column(Date, nullable=True, index=True)
    offer_price_low = Column(Float, nullable=True)
    offer_price_high = Column(Float, nullable=True)
    offer_price_final = Column(Float, nullable=True)
    shares_offered = Column(Float, nullable=True)
    exchange = Column(String(32), nullable=True)
    underwriters = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class MergerEventRow(Base):
    __tablename__ = "merger_events"
    id = Column(String(36), primary_key=True, default=_uuid)
    acquirer_issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True)
    target_issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True)
    announced_date = Column(Date, nullable=True, index=True)
    expected_close = Column(Date, nullable=True)
    actual_close = Column(Date, nullable=True)
    deal_value = Column(Float, nullable=True)
    currency = Column(String(16), default="USD")
    consideration_cash = Column(Float, nullable=True)
    consideration_stock_ratio = Column(Float, nullable=True)
    status = Column(String(32), nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CalendarEventRow(Base):
    """Upcoming-event calendar (polymorphic via ``event_type``)."""

    __tablename__ = "calendar_events"
    id = Column(String(36), primary_key=True, default=_uuid)
    event_type = Column(String(32), nullable=False, index=True)
    # earnings | dividend | split | ipo | economic | buyback | shareholder_meeting | ...
    instrument_id = Column(String(36), ForeignKey("instruments.id"), nullable=True, index=True)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    event_date = Column(Date, nullable=True, index=True)
    event_ts = Column(DateTime, nullable=True)
    title = Column(String(480), nullable=True)
    country = Column(String(32), nullable=True)
    country_iso = Column(String(8), nullable=True)
    importance = Column(Integer, nullable=True)
    actual = Column(Float, nullable=True)
    consensus = Column(Float, nullable=True)
    previous = Column(Float, nullable=True)
    unit = Column(String(32), nullable=True)
    frequency = Column(String(32), nullable=True)
    payload = Column(JSON, default=dict)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_cal_event_type_date", "event_type", "event_date"),
    )


class AnalystEstimate(Base):
    __tablename__ = "analyst_estimates"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    period_ending = Column(Date, nullable=True, index=True)
    fiscal_year = Column(Integer, nullable=True)
    fiscal_period = Column(String(8), nullable=True)
    metric = Column(String(32), nullable=False, default="eps")  # eps | ebitda | pe | sales | revenue | net_income
    avg = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    analyst_count = Column(Integer, nullable=True)
    revision_up = Column(Integer, nullable=True)
    revision_down = Column(Integer, nullable=True)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index(
            "uq_analyst_est",
            "issuer_id",
            "period_ending",
            "metric",
            unique=True,
        ),
    )


class PriceTarget(Base):
    __tablename__ = "price_targets"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    analyst_firm = Column(String(240), nullable=True)
    analyst_name = Column(String(240), nullable=True)
    rating = Column(String(32), nullable=True)
    previous_rating = Column(String(32), nullable=True)
    action = Column(String(32), nullable=True)
    target_price = Column(Float, nullable=True)
    previous_target = Column(Float, nullable=True)
    currency = Column(String(16), default="USD")
    published_ts = Column(DateTime, nullable=True, index=True)
    news_url = Column(String(1024), nullable=True)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ForwardEstimate(Base):
    """Forward-looking consensus estimates (EPS, EBITDA, PE, Sales, …)."""

    __tablename__ = "forward_estimates"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    metric = Column(String(32), nullable=False, index=True)
    fiscal_period = Column(String(8), nullable=True)
    fiscal_year = Column(Integer, nullable=True)
    calendar_year = Column(Integer, nullable=True)
    consensus = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    analyst_count = Column(Integer, nullable=True)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_fwd_est_symbol_metric", "symbol", "metric"),
    )


class RegulatoryEventRow(Base):
    __tablename__ = "regulatory_events"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    jurisdiction = Column(String(64), nullable=True)
    agency = Column(String(120), nullable=True)
    action = Column(String(64), nullable=False, index=True)
    docket_number = Column(String(64), nullable=True)
    amount = Column(Float, nullable=True)
    currency = Column(String(16), default="USD")
    summary = Column(Text, nullable=True)
    url = Column(String(1024), nullable=True)
    published_ts = Column(DateTime, nullable=True, index=True)
    source = Column(String(64), nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EsgEventRow(Base):
    __tablename__ = "esg_events"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    pillar = Column(String(4), nullable=True)  # E | S | G
    sub_score = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=True)
    controversy_level = Column(Integer, nullable=True)
    provider = Column(String(64), nullable=True)
    published_ts = Column(DateTime, nullable=True, index=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
