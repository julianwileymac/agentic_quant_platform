"""Ownership persistence tables (insider, institutional, 13F, short interest, floats)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
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


class InsiderTransactionRow(Base):
    __tablename__ = "insider_transactions"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    company_cik = Column(String(16), nullable=True, index=True)
    filing_date = Column(DateTime, nullable=True, index=True)
    transaction_date = Column(Date, nullable=True, index=True)
    owner_cik = Column(String(16), nullable=True)
    owner_name = Column(String(240), nullable=True)
    owner_title = Column(String(240), nullable=True)
    ownership_type = Column(String(32), nullable=True)
    transaction_type = Column(String(32), nullable=True, index=True)
    acquisition_or_disposition = Column(String(8), nullable=True)
    security_type = Column(String(32), nullable=True)
    securities_owned = Column(Float, nullable=True)
    securities_transacted = Column(Float, nullable=True)
    transaction_price = Column(Float, nullable=True)
    filing_url = Column(String(1024), nullable=True)
    source_filing_accession = Column(String(32), nullable=True, index=True)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_insider_symbol_date", "symbol", "transaction_date"),
    )


class InstitutionalHoldingRow(Base):
    __tablename__ = "institutional_holdings"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    report_date = Column(Date, nullable=True, index=True)
    filer_cik = Column(String(16), nullable=True, index=True)
    filer_name = Column(String(240), nullable=True)
    shares_held = Column(Float, nullable=True)
    market_value = Column(Float, nullable=True)
    percent_of_portfolio = Column(Float, nullable=True)
    change_shares = Column(Float, nullable=True)
    change_pct = Column(Float, nullable=True)
    ownership_type = Column(String(32), nullable=True)
    investor_classification = Column(String(64), nullable=True)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Form13FHoldingRow(Base):
    __tablename__ = "form_13f_holdings"
    id = Column(String(36), primary_key=True, default=_uuid)
    filer_cik = Column(String(16), nullable=False, index=True)
    filer_name = Column(String(240), nullable=True)
    report_date = Column(Date, nullable=False, index=True)
    accession_no = Column(String(32), nullable=False, index=True)
    cusip = Column(String(16), nullable=True, index=True)
    issuer_name = Column(String(240), nullable=True)
    symbol = Column(String(64), nullable=True)
    class_title = Column(String(64), nullable=True)
    shares = Column(Float, nullable=True)
    value_usd = Column(Float, nullable=True)
    put_call = Column(String(8), nullable=True)
    investment_discretion = Column(String(32), nullable=True)
    voting_authority_sole = Column(Float, nullable=True)
    voting_authority_shared = Column(Float, nullable=True)
    voting_authority_none = Column(Float, nullable=True)
    provider = Column(String(64), default="SEC")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_13f_filer_report", "filer_cik", "report_date"),
        Index("ix_13f_cusip_report", "cusip", "report_date"),
    )


class ShortInterestSnapshot(Base):
    __tablename__ = "short_interest_snapshots"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    settlement_date = Column(Date, nullable=False, index=True)
    short_interest_shares = Column(Float, nullable=True)
    average_daily_volume = Column(Float, nullable=True)
    days_to_cover = Column(Float, nullable=True)
    short_percent_float = Column(Float, nullable=True)
    short_percent_outstanding = Column(Float, nullable=True)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("uq_short_interest", "symbol", "settlement_date", unique=True),
    )


class SharesFloatSnapshot(Base):
    __tablename__ = "shares_float_snapshots"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    date = Column(Date, nullable=False, index=True)
    shares_outstanding = Column(Float, nullable=True)
    float_shares = Column(Float, nullable=True)
    restricted_shares = Column(Float, nullable=True)
    percent_insiders = Column(Float, nullable=True)
    percent_institutions = Column(Float, nullable=True)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PoliticianTrade(Base):
    __tablename__ = "politician_trades"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    representative = Column(String(240), nullable=False, index=True)
    chamber = Column(String(16), nullable=True, index=True)
    party = Column(String(16), nullable=True)
    district = Column(String(16), nullable=True)
    transaction_date = Column(Date, nullable=True, index=True)
    disclosure_date = Column(Date, nullable=True)
    transaction_type = Column(String(32), nullable=True)
    amount_low = Column(Float, nullable=True)
    amount_high = Column(Float, nullable=True)
    ownership = Column(String(32), nullable=True)
    notes = Column(Text, nullable=True)
    provider = Column(String(64), nullable=True)
    source_url = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FundHolding(Base):
    """Fund / ETF / mutual fund holdings snapshot."""

    __tablename__ = "fund_holdings"
    id = Column(String(36), primary_key=True, default=_uuid)
    fund_issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    fund_symbol = Column(String(64), nullable=True, index=True)
    holding_issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    holding_symbol = Column(String(64), nullable=True, index=True)
    holding_cusip = Column(String(16), nullable=True)
    as_of = Column(Date, nullable=False, index=True)
    weight = Column(Float, nullable=True)
    shares_held = Column(Float, nullable=True)
    market_value = Column(Float, nullable=True)
    sector = Column(String(120), nullable=True)
    country = Column(String(64), nullable=True)
    asset_class = Column(String(32), nullable=True)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_fund_holdings_fund_date", "fund_symbol", "as_of"),
    )
