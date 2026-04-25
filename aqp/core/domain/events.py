"""Unified domain-event hierarchy.

Every "real-world" event that touches an issuer / instrument flows through
one of the classes in this module: corporate actions, SEC filings, earnings,
insider transactions, institutional holdings updates, analyst ratings,
news, social sentiment, economic observations, regulatory actions, ESG
events, politician trades, commitments of traders, maritime/port volume
alt-data.

All events share the :class:`DomainEvent` base so downstream consumers (Event
Engine, ledger writer, UI swim lane) can treat them uniformly while still
having access to type-specific payloads.

The narrower :class:`aqp.core.slice.CorporateActionEvent` is re-exported
from here so back-compat callers keep working.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as dateType, datetime
from decimal import Decimal
from typing import Any

from aqp.core.domain.enums import (
    CorporateActionKind,
    FilingType,
)
from aqp.core.domain.identifiers import InstrumentId
from aqp.core.domain.issuer import IssuerRef


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


@dataclass
class DomainEvent:
    """Common shape for every real-world event.

    Subclasses should set ``kind`` to a short label (``"filing"``,
    ``"earnings"``, ``"news"``, …) so consumers can demultiplex without
    importing the concrete type. ``ts_event`` is the event's true timestamp;
    ``ts_init`` is when AQP learned about it (useful for look-ahead bias
    audits).
    """

    kind: str = "unknown"
    ts_event: datetime = field(default_factory=datetime.utcnow)
    ts_init: datetime = field(default_factory=datetime.utcnow)
    event_id: str | None = None
    source: str | None = None
    instrument_id: InstrumentId | None = None
    issuer: IssuerRef | None = None
    meta: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Corporate actions
# ---------------------------------------------------------------------------


@dataclass
class CorporateActionEvent(DomainEvent):
    """Split / dividend / spin-off / merger / delisting / rename / buyback.

    Drop-in superset of :class:`aqp.core.slice.CorporateActionEvent`.
    """

    kind: str = "corporate_action"
    action: CorporateActionKind = CorporateActionKind.DIVIDEND
    value: Decimal = Decimal("0")
    ratio: Decimal | None = None
    ex_date: dateType | None = None
    record_date: dateType | None = None
    pay_date: dateType | None = None
    declaration_date: dateType | None = None
    announcement_text: str | None = None
    new_symbol: str | None = None


@dataclass
class DividendDeclarationEvent(DomainEvent):
    kind: str = "dividend_declaration"
    amount: Decimal = Decimal("0")
    currency: str = "USD"
    ex_date: dateType | None = None
    record_date: dateType | None = None
    pay_date: dateType | None = None
    declaration_date: dateType | None = None
    frequency: str | None = None
    is_special: bool = False


@dataclass
class SplitAnnouncementEvent(DomainEvent):
    kind: str = "split_announcement"
    ratio: Decimal = Decimal("1")
    ex_date: dateType | None = None
    record_date: dateType | None = None
    pay_date: dateType | None = None


@dataclass
class IPOEvent(DomainEvent):
    kind: str = "ipo"
    pricing_date: dateType | None = None
    listing_date: dateType | None = None
    offer_price_low: Decimal | None = None
    offer_price_high: Decimal | None = None
    offer_price_final: Decimal | None = None
    shares_offered: Decimal | None = None
    exchange: str | None = None
    underwriters: list[str] = field(default_factory=list)


@dataclass
class MergerEvent(DomainEvent):
    kind: str = "merger"
    acquirer_issuer_id: str | None = None
    target_issuer_id: str | None = None
    announced_date: dateType | None = None
    expected_close: dateType | None = None
    actual_close: dateType | None = None
    deal_value: Decimal | None = None
    currency: str = "USD"
    consideration_cash: Decimal | None = None
    consideration_stock_ratio: Decimal | None = None


# ---------------------------------------------------------------------------
# Filings
# ---------------------------------------------------------------------------


@dataclass
class FilingEvent(DomainEvent):
    """An SEC / regulatory filing."""

    kind: str = "filing"
    filing_type: FilingType = FilingType.CURRENT_REPORT
    form: str = ""
    accession_no: str = ""
    filed_at: datetime | None = None
    period_of_report: dateType | None = None
    primary_doc_url: str | None = None
    primary_doc_type: str | None = None
    xbrl_uri: str | None = None
    items: list[str] = field(default_factory=list)
    text_storage_uri: str | None = None
    is_amendment: bool = False


# ---------------------------------------------------------------------------
# Earnings / estimates / ratings
# ---------------------------------------------------------------------------


@dataclass
class EarningsEvent(DomainEvent):
    kind: str = "earnings"
    fiscal_period: str | None = None  # Q1 2026, FY2025, ...
    fiscal_year: int | None = None
    announcement_ts: datetime | None = None
    call_start_ts: datetime | None = None
    eps_estimate: Decimal | None = None
    eps_actual: Decimal | None = None
    eps_surprise: Decimal | None = None
    eps_surprise_pct: Decimal | None = None
    revenue_estimate: Decimal | None = None
    revenue_actual: Decimal | None = None
    revenue_surprise: Decimal | None = None
    transcript_id: str | None = None


@dataclass
class AnalystRatingEvent(DomainEvent):
    kind: str = "analyst_rating"
    analyst_firm: str | None = None
    analyst_name: str | None = None
    rating: str | None = None  # buy/hold/sell/overweight/neutral
    previous_rating: str | None = None
    action: str | None = None  # initiated | upgraded | downgraded | reiterated
    published_ts: datetime | None = None


@dataclass
class PriceTargetEvent(DomainEvent):
    kind: str = "price_target"
    analyst_firm: str | None = None
    analyst_name: str | None = None
    new_target: Decimal | None = None
    previous_target: Decimal | None = None
    currency: str = "USD"
    target_action: str | None = None  # raised | lowered | maintained | set
    published_ts: datetime | None = None


@dataclass
class ForwardEstimateEvent(DomainEvent):
    kind: str = "forward_estimate"
    metric: str | None = None  # eps | ebitda | pe | sales
    period: str | None = None
    fiscal_year: int | None = None
    consensus: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    analyst_count: int | None = None


# ---------------------------------------------------------------------------
# Ownership events
# ---------------------------------------------------------------------------


@dataclass
class InsiderTransactionEvent(DomainEvent):
    kind: str = "insider_transaction"
    filing_accession: str | None = None
    transaction_date: dateType | None = None
    owner_cik: str | None = None
    owner_name: str | None = None
    owner_title: str | None = None
    ownership_type: str | None = None
    transaction_type: str | None = None
    acquisition_or_disposition: str | None = None
    securities_transacted: Decimal | None = None
    securities_owned_after: Decimal | None = None
    transaction_price: Decimal | None = None


@dataclass
class InstitutionalHoldingEvent(DomainEvent):
    kind: str = "institutional_holding"
    filing_accession: str | None = None
    filer_cik: str | None = None
    filer_name: str | None = None
    report_date: dateType | None = None
    shares_held: Decimal | None = None
    market_value: Decimal | None = None
    percent_of_portfolio: Decimal | None = None
    change_shares: Decimal | None = None
    change_pct: Decimal | None = None


@dataclass
class PoliticianTradeEvent(DomainEvent):
    kind: str = "politician_trade"
    representative: str | None = None
    chamber: str | None = None  # house | senate
    transaction_type: str | None = None
    transaction_date: dateType | None = None
    amount_low: Decimal | None = None
    amount_high: Decimal | None = None
    district: str | None = None
    party: str | None = None


# ---------------------------------------------------------------------------
# News / sentiment / regulatory / ESG
# ---------------------------------------------------------------------------


@dataclass
class NewsEvent(DomainEvent):
    kind: str = "news"
    headline: str = ""
    publisher: str | None = None
    url: str | None = None
    body: str | None = None
    summary: str | None = None
    language: str = "en"
    sentiment_score: float | None = None
    sentiment_label: str | None = None
    entities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class SocialSentimentEvent(DomainEvent):
    kind: str = "social_sentiment"
    platform: str | None = None  # x | reddit | stocktwits
    mentions: int | None = None
    sentiment_score: float | None = None
    sentiment_label: str | None = None
    bullish_pct: float | None = None
    bearish_pct: float | None = None
    window: str | None = None  # 1h | 24h | 7d


@dataclass
class RegulatoryEvent(DomainEvent):
    kind: str = "regulatory"
    jurisdiction: str | None = None
    agency: str | None = None
    action: str | None = None  # investigation | fine | settlement | approval | denial
    docket_number: str | None = None
    amount: Decimal | None = None
    currency: str = "USD"
    published_ts: datetime | None = None


@dataclass
class ESGEvent(DomainEvent):
    kind: str = "esg"
    pillar: str | None = None  # E | S | G
    sub_score: Decimal | None = None
    overall_score: Decimal | None = None
    controversy_level: int | None = None
    provider: str | None = None


# ---------------------------------------------------------------------------
# Macro / alt data
# ---------------------------------------------------------------------------


@dataclass
class EconomicObservationEvent(DomainEvent):
    kind: str = "economic_observation"
    series_id: str = ""
    value: Decimal | None = None
    prior_value: Decimal | None = None
    revised_at: datetime | None = None
    unit: str | None = None
    frequency: str | None = None
    country: str | None = None


@dataclass
class CotReportEvent(DomainEvent):
    kind: str = "cot_report"
    commodity_code: str | None = None
    report_date: dateType | None = None
    commercial_long: Decimal | None = None
    commercial_short: Decimal | None = None
    non_commercial_long: Decimal | None = None
    non_commercial_short: Decimal | None = None
    non_reportable_long: Decimal | None = None
    non_reportable_short: Decimal | None = None


@dataclass
class MaritimeEvent(DomainEvent):
    kind: str = "maritime"
    chokepoint: str | None = None
    vessel_type: str | None = None
    transit_count: int | None = None
    avg_waiting_time_hours: float | None = None
    event_type: str | None = None  # disruption | congestion | reroute


@dataclass
class PortVolumeEvent(DomainEvent):
    kind: str = "port_volume"
    port_name: str | None = None
    country: str | None = None
    throughput_teu: Decimal | None = None
    throughput_tonnes: Decimal | None = None
    period: str | None = None
    year_over_year_pct: Decimal | None = None
