"""Tests for ownership Pydantic models."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from aqp.core.domain.ownership import (
    EquityFtd,
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


def test_insider_transaction():
    t = InsiderTransaction(
        symbol="AAPL",
        company_cik="0000320193",
        transaction_date=date(2025, 3, 10),
        owner_name="Tim Cook",
        owner_title="CEO",
        ownership_type="direct",
        transaction_type="Sale (S)",
        securities_transacted=Decimal("100_000"),
        transaction_price=Decimal("200"),
    )
    assert t.owner_name == "Tim Cook"


def test_institutional_holding():
    h = InstitutionalHolding(
        symbol="AAPL",
        report_date=date(2025, 12, 31),
        filer_name="BlackRock Inc",
        shares_held=Decimal("1_200_000_000"),
        market_value=Decimal("240_000_000_000"),
        percent_of_portfolio=Decimal("5.2"),
    )
    assert h.shares_held > 0


def test_form_13f_holding():
    h = Form13FHolding(
        filer_cik="0001067983",
        filer_name="BERKSHIRE HATHAWAY",
        cusip="037833100",
        report_date=date(2025, 12, 31),
        shares=Decimal("905_000_000"),
        value_usd=Decimal("181_000_000_000"),
    )
    assert h.filer_name == "BERKSHIRE HATHAWAY"


def test_short_interest():
    s = ShortInterest(
        symbol="AAPL",
        settlement_date=date(2025, 12, 15),
        short_interest_shares=Decimal("75_000_000"),
        days_to_cover=Decimal("1.5"),
        short_percent_float=Decimal("0.005"),
    )
    assert s.short_interest_shares == 75_000_000


def test_shares_float():
    f = SharesFloat(
        symbol="AAPL",
        date=date(2025, 12, 31),
        shares_outstanding=Decimal("15_800_000_000"),
        float_shares=Decimal("15_400_000_000"),
        percent_insiders=Decimal("0.02"),
        percent_institutions=Decimal("0.61"),
    )
    assert f.percent_institutions > f.percent_insiders


def test_equity_ownership_snapshot():
    s = EquityOwnershipSnapshot(
        symbol="AAPL",
        date=date(2025, 12, 31),
        institutional_shares=Decimal("9_500_000_000"),
        insider_shares=Decimal("300_000_000"),
        retail_shares=Decimal("5_600_000_000"),
        top_holders_count=500,
    )
    assert s.top_holders_count == 500


def test_equity_peer_group():
    p = EquityPeerGroup(
        symbol="AAPL",
        peer_symbols=["MSFT", "GOOG", "META", "AMZN"],
        selection_method="sector",
        peer_count=4,
    )
    assert len(p.peer_symbols) == 4


def test_government_trade():
    t = GovernmentTrade(
        symbol="AAPL",
        representative="Nancy Pelosi",
        chamber="house",
        party="D",
        transaction_date=date(2025, 3, 15),
        transaction_type="buy",
        amount_low=Decimal("1_000_000"),
        amount_high=Decimal("5_000_000"),
    )
    assert t.amount_high > t.amount_low


def test_equity_ftd():
    f = EquityFtd(
        symbol="AMC",
        cusip="00165C104",
        settlement_date=date(2025, 12, 15),
        quantity=Decimal("500_000"),
    )
    assert f.quantity == 500_000


def test_top_retail():
    t = TopRetail(
        symbol="AAPL",
        platform="robinhood",
        rank=1,
        holders=Decimal("2_300_000"),
        percent_of_portfolios=Decimal("0.15"),
    )
    assert t.rank == 1
