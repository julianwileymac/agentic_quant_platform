"""Polymorphic instrument subclass tables.

Each concrete instrument class stores its shape-specific columns in its own
joined-table subclass, linked to ``instruments.id`` via a 1:1 FK. The parent
:class:`aqp.persistence.models.Instrument` declares
``polymorphic_on=instrument_class``; each subclass sets
``polymorphic_identity`` to match the :class:`aqp.core.domain.enums.InstrumentClass`
value.

Legacy rows that predate this migration carry ``instrument_class = NULL`` and
resolve to the base ``Instrument`` shape — no subclass row is required.
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
    Integer,
    JSON,
    String,
    Text,
)

from aqp.persistence.models import Instrument


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
