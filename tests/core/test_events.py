"""Tests for the unified DomainEvent hierarchy."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from aqp.core.domain.enums import CorporateActionKind, FilingType
from aqp.core.domain.events import (
    AnalystRatingEvent,
    CorporateActionEvent,
    DomainEvent,
    EarningsEvent,
    EconomicObservationEvent,
    FilingEvent,
    IPOEvent,
    InsiderTransactionEvent,
    MergerEvent,
    NewsEvent,
    PoliticianTradeEvent,
    PriceTargetEvent,
    SocialSentimentEvent,
)
from aqp.core.domain.issuer import IssuerRef


def _issuer():
    return IssuerRef(issuer_id="i_aapl", name="Apple Inc", cik="0000320193", country="USA")


def test_domain_event_defaults():
    e = DomainEvent(kind="custom", source="test")
    assert e.kind == "custom"
    assert isinstance(e.ts_event, datetime)
    assert isinstance(e.ts_init, datetime)


def test_corporate_action_event_split():
    e = CorporateActionEvent(
        action=CorporateActionKind.SPLIT,
        ratio=Decimal("4"),
        ex_date=date(2020, 8, 31),
        issuer=_issuer(),
    )
    assert e.kind == "corporate_action"
    assert e.action is CorporateActionKind.SPLIT
    assert e.ratio == 4


def test_filing_event_10k():
    e = FilingEvent(
        filing_type=FilingType.ANNUAL_REPORT,
        form="10-K",
        accession_no="0000320193-24-000001",
        filed_at=datetime(2024, 11, 1),
        issuer=_issuer(),
    )
    assert e.kind == "filing"
    assert e.filing_type is FilingType.ANNUAL_REPORT
    assert e.issuer.cik == "0000320193"


def test_earnings_event_surprise():
    e = EarningsEvent(
        fiscal_period="Q4 2025",
        eps_estimate=Decimal("2.18"),
        eps_actual=Decimal("2.40"),
        issuer=_issuer(),
    )
    assert e.kind == "earnings"
    assert e.eps_actual > e.eps_estimate


def test_ipo_event():
    e = IPOEvent(
        pricing_date=date(2025, 4, 20),
        listing_date=date(2025, 4, 22),
        offer_price_final=Decimal("25"),
        shares_offered=Decimal("10_000_000"),
        exchange="NASDAQ",
    )
    assert e.kind == "ipo"
    assert e.offer_price_final == 25


def test_merger_event():
    e = MergerEvent(
        acquirer_issuer_id="i_acq",
        target_issuer_id="i_tgt",
        deal_value=Decimal("5_000_000_000"),
    )
    assert e.kind == "merger"


def test_insider_transaction_event():
    e = InsiderTransactionEvent(
        transaction_date=date(2025, 3, 10),
        owner_name="Tim Cook",
        owner_title="CEO",
        transaction_type="Sale",
        securities_transacted=Decimal("100_000"),
        transaction_price=Decimal("200"),
        issuer=_issuer(),
    )
    assert e.kind == "insider_transaction"
    assert e.owner_name == "Tim Cook"


def test_analyst_rating_event():
    e = AnalystRatingEvent(
        analyst_firm="Morgan Stanley",
        analyst_name="Jane Doe",
        rating="Overweight",
        previous_rating="Equal-weight",
        action="upgraded",
        issuer=_issuer(),
    )
    assert e.rating == "Overweight"


def test_price_target_event():
    e = PriceTargetEvent(
        analyst_firm="Goldman",
        new_target=Decimal("220"),
        previous_target=Decimal("210"),
        target_action="raised",
        issuer=_issuer(),
    )
    assert e.new_target > e.previous_target


def test_news_event_with_sentiment():
    e = NewsEvent(
        headline="Apple reports record iPhone sales",
        publisher="Bloomberg",
        sentiment_score=0.78,
        sentiment_label="bullish",
        entities=["AAPL"],
    )
    assert e.kind == "news"
    assert e.sentiment_score > 0


def test_social_sentiment_event():
    e = SocialSentimentEvent(
        platform="x",
        mentions=1200,
        sentiment_score=0.35,
        window="24h",
    )
    assert e.platform == "x"


def test_politician_trade_event():
    e = PoliticianTradeEvent(
        representative="Nancy Pelosi",
        chamber="house",
        transaction_type="buy",
        amount_low=Decimal("100_000"),
        amount_high=Decimal("250_000"),
    )
    assert e.kind == "politician_trade"


def test_economic_observation_event():
    e = EconomicObservationEvent(
        series_id="DGS10",
        value=Decimal("4.32"),
        prior_value=Decimal("4.28"),
        unit="percent",
        country="US",
    )
    assert e.series_id == "DGS10"
    assert e.value > e.prior_value
