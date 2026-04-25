"""Ownership / float / short-interest Pydantic models.

Canonical shapes used by the ownership domain (insider transactions, 13F
holdings, institutional holders, short interest, FTDs, government trades,
top retail holdings, peer groups). Mirrors OpenBB's ``insider_trading``,
``institutional_ownership``, ``form_13FHR``, ``equity_short_interest``,
``short_volume``, ``equity_ftd``, ``government_trades``, ``top_retail``,
``equity_peers``, ``equity_ownership`` standard_models.
"""
from __future__ import annotations

from datetime import date as dateType, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class _OwnershipBase(BaseModel):
    """Shared config + audit fields."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, arbitrary_types_allowed=True)
    symbol: str | None = None
    issuer_id: str | None = None
    source: str | None = None
    provider: str | None = None
    as_of: datetime | None = None


class InsiderTransaction(_OwnershipBase):
    """Form 4 / Form 144 style insider transaction."""

    company_cik: str | None = None
    filing_date: dateType | datetime | None = None
    transaction_date: dateType | None = None
    owner_cik: str | None = None
    owner_name: str | None = None
    owner_title: str | None = None
    ownership_type: str | None = None
    transaction_type: str | None = None
    acquisition_or_disposition: str | None = None
    security_type: str | None = None
    securities_owned: Decimal | None = None
    securities_transacted: Decimal | None = None
    transaction_price: Decimal | None = None
    filing_url: str | None = None


class InstitutionalHolding(_OwnershipBase):
    """Generic institutional holding snapshot."""

    report_date: dateType | None = None
    filer_name: str | None = None
    filer_cik: str | None = None
    shares_held: Decimal | None = None
    market_value: Decimal | None = None
    percent_of_portfolio: Decimal | None = None
    change_shares: Decimal | None = None
    change_pct: Decimal | None = None
    ownership_type: str | None = None
    investor_classification: str | None = None


class Form13FHolding(_OwnershipBase):
    """Form 13F-HR line item."""

    report_date: dateType | None = None
    filer_cik: str | None = None
    filer_name: str | None = None
    cusip: str | None = None
    issuer_name: str | None = None
    class_title: str | None = None
    shares: Decimal | None = None
    value_usd: Decimal | None = None
    put_call: str | None = None
    investment_discretion: str | None = None
    voting_authority_sole: Decimal | None = None
    voting_authority_shared: Decimal | None = None
    voting_authority_none: Decimal | None = None


class ShortInterest(_OwnershipBase):
    """FINRA-style short-interest snapshot."""

    settlement_date: dateType | None = None
    short_interest_shares: Decimal | None = None
    average_daily_volume: Decimal | None = None
    days_to_cover: Decimal | None = None
    short_percent_float: Decimal | None = None
    short_percent_outstanding: Decimal | None = None


class SharesFloat(_OwnershipBase):
    """Shares outstanding / float snapshot."""

    date: dateType | None = None
    shares_outstanding: Decimal | None = None
    float_shares: Decimal | None = None
    restricted_shares: Decimal | None = None
    percent_insiders: Decimal | None = None
    percent_institutions: Decimal | None = None


class EquityOwnershipSnapshot(_OwnershipBase):
    """Aggregated ownership breakdown for a company at a moment in time."""

    date: dateType | None = None
    institutional_shares: Decimal | None = None
    insider_shares: Decimal | None = None
    retail_shares: Decimal | None = None
    top_holders_count: int | None = None
    shares_float: Decimal | None = None
    shares_outstanding: Decimal | None = None


class EquityPeerGroup(_OwnershipBase):
    """Peer-group construction for comparative analysis."""

    peer_symbols: list[str] = Field(default_factory=list)
    selection_method: str | None = None  # sector | industry | size | custom
    peer_count: int | None = None


class GovernmentTrade(_OwnershipBase):
    """Politician / government-insider trade (STOCK Act disclosures)."""

    representative: str | None = None
    chamber: str | None = None  # house | senate
    party: str | None = None
    district: str | None = None
    transaction_date: dateType | None = None
    disclosure_date: dateType | None = None
    transaction_type: str | None = None
    amount_low: Decimal | None = None
    amount_high: Decimal | None = None
    ownership: str | None = None
    notes: str | None = None


class EquityFtd(_OwnershipBase):
    """Fails-to-deliver row."""

    settlement_date: dateType | None = None
    cusip: str | None = None
    quantity: Decimal | None = None
    description: str | None = None


class TopRetail(_OwnershipBase):
    """Top-retail-held snapshot (from retail platforms)."""

    platform: str | None = None
    rank: int | None = None
    holders: Decimal | None = None
    holders_change: Decimal | None = None
    percent_of_portfolios: Decimal | None = None
