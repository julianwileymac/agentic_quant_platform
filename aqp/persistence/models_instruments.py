"""Polymorphic instrument subclass tables.

Each concrete instrument class stores its shape-specific columns in its own
joined-table subclass, linked to ``instruments.id`` via a 1:1 FK. The parent
:class:`aqp.persistence.models.Instrument` declares
``polymorphic_on=instrument_class``; each subclass sets
``polymorphic_identity`` to match the :class:`aqp.core.domain.enums.InstrumentClass`
value.

Legacy rows that predate this migration carry ``instrument_class = NULL`` and
resolve to the base ``Instrument`` shape — no subclass row is required.

Phase 1 (migration 0039) adds first-class joined tables for REITs, mutual
funds, OTC derivatives, ADRs, and GDRs so the report-mandated extended
taxonomy can be queried without re-purposing ``InstrumentEquity`` columns.
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
    UniqueConstraint,
)

from aqp.persistence.models import Base, Instrument, _uuid


# ---------------------------------------------------------------------------
# Equity family
# ---------------------------------------------------------------------------


class InstrumentEquity(Instrument):
    __tablename__ = "instrument_equity"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    issuer_cik = Column(String(16), nullable=True, index=True)
    isin = Column(String(16), nullable=True, index=True)
    cusip = Column(String(16), nullable=True, index=True)
    figi = Column(String(16), nullable=True, index=True)
    lei = Column(String(20), nullable=True, index=True)
    share_class = Column(String(16), nullable=True)
    primary_listing_venue = Column(String(32), nullable=True)
    listing_date = Column(Date, nullable=True)
    delisting_date = Column(Date, nullable=True)
    shares_outstanding = Column(Float, nullable=True)
    float_shares = Column(Float, nullable=True)
    is_adr = Column(Boolean, default=False, nullable=False)
    country = Column(String(64), nullable=True)
    gics_sector = Column(String(120), nullable=True)
    gics_industry = Column(String(120), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "spot"}


class InstrumentETF(Instrument):
    __tablename__ = "instrument_etf"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    issuer_fund_id = Column(String(36), nullable=True, index=True)
    inception_date = Column(Date, nullable=True)
    aum = Column(Float, nullable=True)
    expense_ratio = Column(Float, nullable=True)
    underlying_index = Column(String(120), nullable=True)
    holdings_ref = Column(String(240), nullable=True)
    is_leveraged = Column(Boolean, default=False)
    leverage = Column(Float, nullable=True)
    is_inverse = Column(Boolean, default=False)
    replication = Column(String(32), nullable=True)
    country = Column(String(64), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "etf"}


class InstrumentIndex(Instrument):
    __tablename__ = "instrument_index"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    administrator = Column(String(120), nullable=True)
    methodology = Column(Text, nullable=True)
    constituent_count = Column(Integer, nullable=True)
    base_date = Column(Date, nullable=True)
    base_value = Column(Float, nullable=True)

    __mapper_args__ = {"polymorphic_identity": "index"}


# ---------------------------------------------------------------------------
# Fixed income
# ---------------------------------------------------------------------------


class InstrumentBond(Instrument):
    __tablename__ = "instrument_bond"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    coupon = Column(Float, nullable=True)
    coupon_frequency = Column(String(24), nullable=True)
    maturity = Column(Date, nullable=True)
    issue_date = Column(Date, nullable=True)
    face_value = Column(Float, nullable=True)
    day_count = Column(String(16), nullable=True)
    seniority = Column(String(32), nullable=True)
    rating_sp = Column(String(16), nullable=True)
    rating_moodys = Column(String(16), nullable=True)
    rating_fitch = Column(String(16), nullable=True)
    callable = Column(Boolean, default=False)
    putable = Column(Boolean, default=False)
    convertible = Column(Boolean, default=False)
    is_inflation_linked = Column(Boolean, default=False)
    country = Column(String(64), nullable=True)
    bond_class = Column(String(32), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "bond"}


# ---------------------------------------------------------------------------
# Futures
# ---------------------------------------------------------------------------


class InstrumentFuture(Instrument):
    __tablename__ = "instrument_future"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    underlying = Column(String(64), nullable=True, index=True)
    expiry = Column(Date, nullable=True, index=True)
    first_trade = Column(Date, nullable=True)
    last_trade = Column(Date, nullable=True)
    contract_size = Column(Float, nullable=True)
    settlement_type = Column(String(16), nullable=True)
    cycle = Column(String(32), nullable=True)
    exchange_product_code = Column(String(32), nullable=True)
    delivery_month = Column(String(16), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "future"}


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------


class InstrumentOption(Instrument):
    __tablename__ = "instrument_option"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    underlying = Column(String(64), nullable=True, index=True)
    strike = Column(Float, nullable=True, index=True)
    expiry = Column(Date, nullable=True, index=True)
    kind = Column(String(16), nullable=False, default="call")  # call | put | straddle
    style = Column(String(16), nullable=True)  # european | american | bermudan | asian
    contract_size = Column(Float, nullable=True, default=100)
    settlement_type = Column(String(16), nullable=True)
    exercise_price = Column(Float, nullable=True)
    occ_symbol = Column(String(32), nullable=True)
    option_portfolio = Column(String(64), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "option"}


# ---------------------------------------------------------------------------
# FX
# ---------------------------------------------------------------------------


class InstrumentFxPair(Instrument):
    __tablename__ = "instrument_fx_pair"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    base_currency = Column(String(16), nullable=False)
    quote_currency = Column(String(16), nullable=False)
    pip_size = Column(Float, nullable=True)
    contract_size = Column(Float, nullable=True)

    __mapper_args__ = {"polymorphic_identity": "fx_pair"}


# ---------------------------------------------------------------------------
# Crypto family
# ---------------------------------------------------------------------------


class InstrumentCrypto(Instrument):
    """Catch-all for :class:`CryptoToken`/``CryptoPerpetual`` / etc.

    Specific sub-shape is captured by the ``subtype`` column
    (``spot`` | ``perpetual`` | ``future`` | ``option``).
    """

    __tablename__ = "instrument_crypto"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    subtype = Column(String(16), nullable=True, index=True)
    underlying = Column(String(64), nullable=True)
    chain = Column(String(64), nullable=True)
    contract_address = Column(String(128), nullable=True)
    decimals = Column(Integer, nullable=True)
    settlement_currency = Column(String(16), nullable=True)
    expiry = Column(DateTime, nullable=True)
    funding_interval = Column(String(16), nullable=True)
    max_leverage = Column(Float, nullable=True)
    maker_fee = Column(Float, nullable=True)
    taker_fee = Column(Float, nullable=True)
    is_inverse = Column(Boolean, default=False)
    is_native = Column(Boolean, default=False)
    cmc_id = Column(Integer, nullable=True)
    coingecko_id = Column(String(64), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "crypto_token"}


# ---------------------------------------------------------------------------
# CFD / commodity / synthetic
# ---------------------------------------------------------------------------


class InstrumentCfd(Instrument):
    __tablename__ = "instrument_cfd"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    underlying = Column(String(64), nullable=True)
    contract_size = Column(Float, nullable=True)
    margin_rate = Column(Float, nullable=True)
    financing_rate = Column(Float, nullable=True)

    __mapper_args__ = {"polymorphic_identity": "cfd"}


class InstrumentCommodity(Instrument):
    __tablename__ = "instrument_commodity"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    grade = Column(String(64), nullable=True)
    unit_of_measure = Column(String(32), nullable=True)
    delivery = Column(String(64), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "spot_commodity"}


class InstrumentSynthetic(Instrument):
    __tablename__ = "instrument_synthetic"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    legs = Column(JSON, default=list)  # list[vt_symbol]
    leg_weights = Column(JSON, default=dict)
    formula = Column(Text, nullable=True)

    __mapper_args__ = {"polymorphic_identity": "synthetic"}


# ---------------------------------------------------------------------------
# Event / tokenized
# ---------------------------------------------------------------------------


class InstrumentBetting(Instrument):
    __tablename__ = "instrument_betting"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    event_type = Column(String(64), nullable=True)
    event_name = Column(String(240), nullable=True)
    event_open = Column(DateTime, nullable=True)
    market_id = Column(String(64), nullable=True)
    market_name = Column(String(240), nullable=True)
    market_type = Column(String(64), nullable=True)
    market_start = Column(DateTime, nullable=True)
    selection_id = Column(String(64), nullable=True)
    selection_name = Column(String(240), nullable=True)
    selection_handicap = Column(Float, nullable=True)
    competition = Column(String(120), nullable=True)
    country_code = Column(String(8), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "betting"}


class InstrumentTokenizedAsset(Instrument):
    __tablename__ = "instrument_tokenized_asset"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    chain = Column(String(64), nullable=True)
    contract_address = Column(String(128), nullable=True)
    token_standard = Column(String(32), nullable=True)
    supply = Column(Integer, nullable=True)
    reference_asset = Column(String(240), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "nft"}


# ---------------------------------------------------------------------------
# Phase 1 (migration 0039): extended taxonomy
# ---------------------------------------------------------------------------


class InstrumentREIT(Instrument):
    """Real estate investment trust.

    REITs trade like an equity but carry a separate set of fundamental
    measures: funds-from-operations (FFO), distribution yield, payout
    ratio, and a property-portfolio composition that the LLM-router
    needs to reason about for sector-rotation strategies. Storing the
    portfolio as ``property_portfolio_json`` keeps the row narrow while
    still letting the discovery service surface "what properties are in
    this REIT?" without spinning up a separate ``reit_properties``
    table.
    """

    __tablename__ = "instrument_reit"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    issuer_cik = Column(String(16), nullable=True)
    isin = Column(String(16), nullable=True, index=True)
    cusip = Column(String(16), nullable=True, index=True)
    figi = Column(String(16), nullable=True)
    lei = Column(String(20), nullable=True)
    reit_class = Column(String(32), nullable=True)
    # equity | mortgage | hybrid | public_non_listed | private
    property_sector = Column(String(64), nullable=True, index=True)
    property_portfolio_json = Column(JSON, default=list)
    distribution_yield = Column(Float, nullable=True)
    ffo_per_share = Column(Float, nullable=True)
    nav_per_share = Column(Float, nullable=True)
    payout_ratio = Column(Float, nullable=True)
    debt_to_equity = Column(Float, nullable=True)
    listing_date = Column(Date, nullable=True)
    country = Column(String(64), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "reit"}


class InstrumentMutualFund(Instrument):
    """Open-ended / closed-end mutual fund.

    Distinct from :class:`InstrumentETF` because the trading mechanism
    differs (end-of-day NAV pricing for open-end funds vs continuous
    creation-redemption for ETFs) and the relevant fundamentals (expense
    ratio, management fee, minimum investment, share class) live in
    different fields. Closed-end funds (``fund_kind='closed_end'``) trade
    intraday but still settle against the parent NAV.
    """

    __tablename__ = "instrument_mutual_fund"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    issuer_fund_id = Column(String(36), nullable=True)
    fund_family = Column(String(120), nullable=True, index=True)
    share_class = Column(String(16), nullable=True)
    inception_date = Column(Date, nullable=True)
    aum = Column(Float, nullable=True)
    expense_ratio = Column(Float, nullable=True)
    management_fee = Column(Float, nullable=True)
    nav_currency = Column(String(16), nullable=True)
    minimum_investment = Column(Float, nullable=True)
    minimum_subsequent_investment = Column(Float, nullable=True)
    fund_kind = Column(String(32), nullable=True, index=True)
    investment_strategy = Column(String(64), nullable=True)
    benchmark_index = Column(String(120), nullable=True, index=True)
    is_index_fund = Column(Boolean, default=False, nullable=False)
    is_actively_managed = Column(Boolean, default=True, nullable=False)
    distribution_frequency = Column(String(24), nullable=True)
    country = Column(String(64), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "mutual_fund"}


class InstrumentOTCDerivative(Instrument):
    """Over-the-counter (OTC) derivative.

    Spans swaps, swaptions, caps/floors, exotic forwards, variance swaps,
    CDS, total return swaps, basket swaps. The ``instrument_kind``
    discriminator carries the specific shape; ``legs_json`` stores the
    leg structure (pay/receive, leg type, currency, rate index) without
    a separate ``otc_legs`` child table.

    The row is keyed by the platform's vt_symbol but the regulatory
    identity flows through ``counterparty_lei`` + ``isda_master_agreement_id``
    so reconciliation against trade-repository feeds (DTCC, REGIS-TR)
    works without a separate registration step.
    """

    __tablename__ = "instrument_otc_derivative"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    instrument_kind = Column(String(32), nullable=False, index=True)
    # swap | swaption | cap_floor | forward | exotic | variance_swap |
    # credit_default_swap | total_return_swap | basket_swap
    counterparty_lei = Column(String(20), nullable=True, index=True)
    counterparty_name = Column(String(240), nullable=True)
    isda_master_agreement_id = Column(String(64), nullable=True)
    isda_schedule_version = Column(String(16), nullable=True)
    notional_currency = Column(String(16), nullable=True)
    notional_amount = Column(Float, nullable=True)
    settlement_currency = Column(String(16), nullable=True)
    trade_date = Column(Date, nullable=True)
    effective_date = Column(Date, nullable=True)
    termination_date = Column(Date, nullable=True, index=True)
    payment_frequency = Column(String(24), nullable=True)
    collateral_type = Column(String(32), nullable=True)
    cleared = Column(Boolean, default=False, nullable=False)
    ccp_name = Column(String(120), nullable=True)
    legs_json = Column(JSON, default=list)
    payoff_formula = Column(Text, nullable=True)

    __mapper_args__ = {"polymorphic_identity": "otc_derivative"}


class InstrumentADR(Instrument):
    """American Depositary Receipt.

    Distinct from a regular :class:`InstrumentEquity` with ``is_adr=True``
    because the ADR carries (a) a FK back to the underlying foreign
    equity row and (b) a conversion ratio that the cross-market basis
    algorithm needs to read directly to compute the implied basis spread.
    Sponsorship-level governance (I/II/III/144A/Reg_S) lives here so the
    risk engine can flag unsponsored ADRs (which carry weaker holder
    protections) without re-reading the entity metadata.

    The legacy ``InstrumentEquity.is_adr`` flag is kept for backward
    compatibility — it's now derived from the presence of a row in this
    table.
    """

    __tablename__ = "instrument_adr"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    underlying_instrument_id = Column(
        String(36), ForeignKey("instruments.id"), nullable=True, index=True
    )
    underlying_ticker = Column(String(64), nullable=True)
    underlying_venue = Column(String(32), nullable=True)
    underlying_isin = Column(String(16), nullable=True, index=True)
    conversion_ratio = Column(Float, nullable=False, default=1.0)
    depository_bank_name = Column(String(120), nullable=True)
    depository_bank_lei = Column(String(20), nullable=True)
    sponsorship_level = Column(String(16), nullable=True, index=True)
    # I | II | III | 144A | Reg_S | unsponsored
    listing_venue = Column(String(32), nullable=True)
    custodian_country = Column(String(64), nullable=True)
    home_country = Column(String(64), nullable=True)
    annual_dr_fee = Column(Float, nullable=True)
    created_date = Column(Date, nullable=True)
    issuer_cik = Column(String(16), nullable=True)
    isin = Column(String(16), nullable=True, index=True)
    cusip = Column(String(16), nullable=True)
    figi = Column(String(16), nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "adr",
        # Two FKs to ``instruments.id`` (own row + underlying); tell the
        # mapper which one belongs to the joined-table inheritance.
        "inherit_condition": id == Instrument.id,
    }


class InstrumentGDR(Instrument):
    """Global Depositary Receipt.

    Structurally identical to :class:`InstrumentADR` but with
    different listing-regime metadata (regulatory regime: Reg_S /
    Rule_144A / Reg_S_144A / full_listing) and typically a non-US
    listing venue (LSE, LuxSE, Frankfurt, SIX, Singapore, Dubai). Kept
    as a separate joined table so cross-market arbitrage strategies can
    discriminate between ADR-specific (SEC-registered) and GDR-specific
    (offshore) regulatory regimes at the SQL level.
    """

    __tablename__ = "instrument_gdr"
    id = Column(String(36), ForeignKey("instruments.id"), primary_key=True)
    underlying_instrument_id = Column(
        String(36), ForeignKey("instruments.id"), nullable=True, index=True
    )
    underlying_ticker = Column(String(64), nullable=True)
    underlying_venue = Column(String(32), nullable=True)
    underlying_isin = Column(String(16), nullable=True, index=True)
    conversion_ratio = Column(Float, nullable=False, default=1.0)
    depository_bank_name = Column(String(120), nullable=True)
    depository_bank_lei = Column(String(20), nullable=True)
    listing_venue = Column(String(32), nullable=True)
    regulatory_regime = Column(String(32), nullable=True, index=True)
    # Reg_S | Rule_144A | Reg_S_144A | full_listing
    custodian_country = Column(String(64), nullable=True)
    home_country = Column(String(64), nullable=True)
    annual_dr_fee = Column(Float, nullable=True)
    created_date = Column(Date, nullable=True)
    issuer_cik = Column(String(16), nullable=True)
    isin = Column(String(16), nullable=True, index=True)
    cusip = Column(String(16), nullable=True)
    figi = Column(String(16), nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "gdr",
        "inherit_condition": id == Instrument.id,
    }


# ---------------------------------------------------------------------------
# Phase 1 (migration 0039): instrument_measures registry
# ---------------------------------------------------------------------------


class InstrumentMeasure(Base):
    """Catalog of measurable quantities exposed on an instrument.

    One row per ``(instrument_id, measure_type, frequency, dataset_field)``
    tuple. Used by the DataMCP tool ``data.instruments.measures`` so an
    LLM-routed agent can answer "what daily metrics are available for
    AAPL?" before it generates a SQL / Iceberg query and risks selecting
    a column that doesn't exist.

    The catalog is intentionally a registry, not a dataset — the actual
    measure values live in their source datasets (bars, options chain
    snapshots, fundamental statements). Each row points back to the
    source dataset via ``source_dataset_id`` so the resolver can render
    a join path automatically.
    """

    __tablename__ = "instrument_measures"
    id = Column(String(36), primary_key=True, default=_uuid)
    instrument_id = Column(
        String(36),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    measure_type = Column(String(64), nullable=False, index=True)
    # price | volume | open_interest | implied_volatility | dividend_yield |
    # earnings_yield | book_value | ffo | nav | distribution | greek_delta |
    # greek_gamma | basis | spread | turnover | bid_ask_spread | ...
    frequency = Column(String(32), nullable=False, index=True)
    # tick | second | minute | hour | day | week | month | quarter | annual |
    # event_driven | adhoc
    dataset_field = Column(String(120), nullable=False)
    source_dataset_id = Column(
        String(36),
        ForeignKey("dataset_catalogs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    unit = Column(String(32), nullable=True)
    description = Column(Text, nullable=True)
    first_available = Column(DateTime, nullable=True)
    last_available = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "measure_type",
            "frequency",
            "dataset_field",
            name="uq_instrument_measures_address",
        ),
        Index(
            "ix_instrument_measures_address",
            "instrument_id",
            "measure_type",
            "frequency",
        ),
    )


__all__ = [
    "InstrumentADR",
    "InstrumentBetting",
    "InstrumentBond",
    "InstrumentCfd",
    "InstrumentCommodity",
    "InstrumentCrypto",
    "InstrumentETF",
    "InstrumentEquity",
    "InstrumentFuture",
    "InstrumentFxPair",
    "InstrumentGDR",
    "InstrumentIndex",
    "InstrumentMeasure",
    "InstrumentMutualFund",
    "InstrumentOption",
    "InstrumentOTCDerivative",
    "InstrumentREIT",
    "InstrumentSynthetic",
    "InstrumentTokenizedAsset",
]
