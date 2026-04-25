"""Polymorphic ``Instrument`` hierarchy.

This is the keystone of the expanded domain model. Every tradable asset is a
subclass of :class:`Instrument` and carries both the generic metadata (id,
venue, issuer, currency, tick size, multiplier, trading hours) and
instrument-class-specific fields (expiry for futures, strike for options,
underlying for spreads, chain info for crypto tokens, selection info for
betting markets, …).

Dispatch is done by a ``(AssetClass, InstrumentClass) -> class`` registry
mirroring gs-quant's ``__asset_class_and_type_to_instrument`` so YAML recipes
that say::

    {class: "Equity", kwargs: {symbol: "AAPL", venue: "NASDAQ"}}

can be routed by :func:`aqp.core.registry.build_from_config` without a
hand-written factory — the registry maps to the correct subclass via
:func:`instrument_class_for`.

Every subclass remains a simple ``@dataclass`` so they are trivially JSON-
serialisable and safe to pass between Celery workers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as dateType, datetime
from decimal import Decimal
from typing import Any, ClassVar

from aqp.core.domain.enums import (
    AssetClass,
    InstrumentClass,
    OptionKind,
    OptionStyle,
    PayReceive,
    Product,
    SettlementType,
)
from aqp.core.domain.identifiers import (
    IdentifierScheme,
    IdentifierSet,
    IdentifierValue,
    InstrumentId,
)
from aqp.core.domain.money import Currency, currency_of


# ---------------------------------------------------------------------------
# Registry: (AssetClass, InstrumentClass) -> class
# ---------------------------------------------------------------------------


_INSTRUMENT_REGISTRY: dict[tuple[AssetClass, InstrumentClass], type["Instrument"]] = {}


def register_instrument_class(
    asset_class: AssetClass,
    instrument_class: InstrumentClass,
) -> Any:
    """Class decorator that registers a subclass under ``(asset_class, instrument_class)``.

    Lookup is via :func:`instrument_class_for`; collisions raise at
    registration time to catch accidental double-registration early.
    """

    def _wrap(cls: type["Instrument"]) -> type["Instrument"]:
        key = (asset_class, instrument_class)
        existing = _INSTRUMENT_REGISTRY.get(key)
        if existing is not None and existing is not cls:
            raise RuntimeError(
                f"Instrument registry conflict for {key}: {existing!r} vs {cls!r}"
            )
        _INSTRUMENT_REGISTRY[key] = cls
        cls._registered_asset_class = asset_class  # type: ignore[attr-defined]
        cls._registered_instrument_class = instrument_class  # type: ignore[attr-defined]
        return cls

    return _wrap


def instrument_class_for(
    asset_class: AssetClass | str,
    instrument_class: InstrumentClass | str,
) -> type["Instrument"] | None:
    """Return the registered :class:`Instrument` subclass for a given pair."""
    ac = asset_class if isinstance(asset_class, AssetClass) else AssetClass(asset_class)
    ic = (
        instrument_class
        if isinstance(instrument_class, InstrumentClass)
        else InstrumentClass(instrument_class)
    )
    return _INSTRUMENT_REGISTRY.get((ac, ic))


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


@dataclass
class InstrumentBase:
    """Shared metadata present on every :class:`Instrument`.

    Kept separate from :class:`Instrument` so back-compat ``Instrument`` SQL
    rows can materialize to this lightweight carrier when the full
    polymorphic row isn't loaded yet.
    """

    instrument_id: InstrumentId
    asset_class: AssetClass
    instrument_class: InstrumentClass
    name: str = ""
    currency: Currency = field(default_factory=lambda: currency_of("USD"))
    tick_size: Decimal = field(default_factory=lambda: Decimal("0.01"))
    multiplier: Decimal = field(default_factory=lambda: Decimal("1"))
    min_quantity: Decimal = field(default_factory=lambda: Decimal("1"))
    max_quantity: Decimal | None = None
    lot_size: Decimal = field(default_factory=lambda: Decimal("1"))
    price_precision: int = 2
    size_precision: int = 0
    is_active: bool = True
    identifiers: IdentifierSet = field(default_factory=IdentifierSet)
    tags: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def venue(self) -> str:
        return self.instrument_id.venue.value

    @property
    def symbol(self) -> str:
        return self.instrument_id.symbol.value

    @property
    def vt_symbol(self) -> str:
        return self.instrument_id.vt_symbol

    def add_identifier(
        self,
        scheme: IdentifierScheme | str,
        value: str,
        *,
        confidence: float = 1.0,
        source: str | None = None,
    ) -> None:
        self.identifiers.add(
            IdentifierValue(
                scheme=scheme if isinstance(scheme, IdentifierScheme) else IdentifierScheme(scheme),
                value=value,
                confidence=confidence,
                source=source,
            )
        )

    def identifier(self, scheme: IdentifierScheme | str) -> str | None:
        return self.identifiers.value_of(scheme)


@dataclass
class Instrument(InstrumentBase):
    """Abstract root of the polymorphic instrument tree.

    Most callers interact via one of the concrete subclasses (:class:`Equity`,
    :class:`FuturesContract`, :class:`OptionContract`, …). Subclasses MUST be
    registered via :func:`register_instrument_class` so ``(asset_class,
    instrument_class)`` lookups resolve to the right row shape.
    """

    # Marker so subclasses can override without re-declaring every field.
    _registered_asset_class: ClassVar[AssetClass | None] = None
    _registered_instrument_class: ClassVar[InstrumentClass | None] = None

    @classmethod
    def product(cls) -> Product | None:
        """Most subclasses set this to feed into vnpy-parity ``ContractData``."""
        return None


# ---------------------------------------------------------------------------
# Equity family
# ---------------------------------------------------------------------------


@dataclass
@register_instrument_class(AssetClass.EQUITY, InstrumentClass.SPOT)
class Equity(Instrument):
    """Listed equity security (common stock, preferred, foreign ordinaries).

    ``issuer_id`` links back to a row in the ``issuers`` persistence table —
    the in-memory model mirrors OpenBB's ``EquityInfoData`` so every field
    the platform might expose on a company page has a home here or on the
    referenced :class:`~aqp.core.domain.issuer.Issuer`.
    """

    issuer_id: str | None = None
    primary_listing_venue: str | None = None
    share_class: str | None = None
    cik: str | None = None
    isin: str | None = None
    cusip: str | None = None
    sedol: str | None = None
    figi: str | None = None
    lei: str | None = None
    listing_date: dateType | None = None
    delisting_date: dateType | None = None
    shares_outstanding: Decimal | None = None
    float_shares: Decimal | None = None
    is_adr: bool = False
    country: str | None = None
    sector: str | None = None
    industry: str | None = None

    @classmethod
    def product(cls) -> Product | None:
        return Product.SPOT


@dataclass
@register_instrument_class(AssetClass.EQUITY, InstrumentClass.ETF)
class ETF(Instrument):
    """Exchange-traded fund."""

    issuer_id: str | None = None
    inception: dateType | None = None
    aum: Decimal | None = None
    expense_ratio: Decimal | None = None
    holdings_ref: str | None = None
    underlying_index: str | None = None
    is_leveraged: bool = False
    leverage: Decimal | None = None
    is_inverse: bool = False
    replication: str | None = None  # physical | synthetic | sampled
    country: str | None = None

    @classmethod
    def product(cls) -> Product | None:
        return Product.ETF


@dataclass
@register_instrument_class(AssetClass.INDEX, InstrumentClass.INDEX)
class IndexInstrument(Instrument):
    """A price index (^SPX, ^NDX, ^VIX). Non-tradable directly."""

    methodology: str | None = None
    administrator: str | None = None
    constituent_count: int | None = None
    inception: dateType | None = None

    @classmethod
    def product(cls) -> Product | None:
        return Product.INDEX


# ---------------------------------------------------------------------------
# Fixed income
# ---------------------------------------------------------------------------


@dataclass
@register_instrument_class(AssetClass.RATES, InstrumentClass.BOND)
class Bond(Instrument):
    """Corporate, government, or supranational bond."""

    issuer_id: str | None = None
    coupon: Decimal | None = None
    coupon_frequency: str | None = None  # annual, semi_annual, quarterly, monthly
    maturity: dateType | None = None
    issue_date: dateType | None = None
    face_value: Decimal = field(default_factory=lambda: Decimal("1000"))
    day_count: str | None = None  # act/360, 30/360, act/act, ...
    seniority: str | None = None
    rating_sp: str | None = None
    rating_moodys: str | None = None
    rating_fitch: str | None = None
    callable: bool = False
    putable: bool = False
    convertible: bool = False
    is_inflation_linked: bool = False
    country: str | None = None
    bond_class: str | None = None  # corporate | government | municipal | supranational | agency

    @classmethod
    def product(cls) -> Product | None:
        return Product.BOND


# ---------------------------------------------------------------------------
# Futures
# ---------------------------------------------------------------------------


@dataclass
@register_instrument_class(AssetClass.COMMODITY, InstrumentClass.FUTURE)
class FuturesContract(Instrument):
    """Dated futures contract (commodity, equity index, interest rate, …)."""

    underlying: str | None = None
    expiry: dateType | None = None
    first_trade: dateType | None = None
    last_trade: dateType | None = None
    contract_size: Decimal = field(default_factory=lambda: Decimal("1"))
    settlement_type: SettlementType = SettlementType.PHYSICAL
    cycle: str | None = None  # e.g. "quarterly", "monthly"
    exchange_product_code: str | None = None
    delivery_month: str | None = None

    @classmethod
    def product(cls) -> Product | None:
        return Product.FUTURES


@dataclass
@register_instrument_class(AssetClass.COMMODITY, InstrumentClass.SPREAD)
class FuturesSpread(Instrument):
    """Calendar / inter-commodity futures spread."""

    legs: list[FuturesContract] = field(default_factory=list)
    spread_type: str | None = None  # calendar | inter_commodity | butterfly | condor

    @classmethod
    def product(cls) -> Product | None:
        return Product.SPREAD


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------


@dataclass
@register_instrument_class(AssetClass.EQUITY, InstrumentClass.OPTION)
class OptionContract(Instrument):
    """Listed option on a single underlying."""

    underlying: str | None = None
    strike: Decimal | None = None
    expiry: dateType | None = None
    kind: OptionKind = OptionKind.CALL
    style: OptionStyle = OptionStyle.AMERICAN
    contract_size: Decimal = field(default_factory=lambda: Decimal("100"))
    settlement_type: SettlementType = SettlementType.PHYSICAL
    exercise_price: Decimal | None = None
    option_portfolio: str | None = None
    occ_symbol: str | None = None

    @classmethod
    def product(cls) -> Product | None:
        return Product.OPTION


@dataclass
@register_instrument_class(AssetClass.EQUITY, InstrumentClass.SPREAD)
class OptionSpread(Instrument):
    """Multi-leg option strategy (spread/butterfly/condor/strangle/straddle)."""

    legs: list[OptionContract] = field(default_factory=list)
    spread_type: str | None = None

    @classmethod
    def product(cls) -> Product | None:
        return Product.SPREAD


@dataclass
@register_instrument_class(AssetClass.EQUITY, InstrumentClass.BINARY_OPTION)
class BinaryOption(Instrument):
    """Digital option that pays a fixed amount if ITM at expiry."""

    underlying: str | None = None
    strike: Decimal | None = None
    expiry: datetime | None = None
    kind: OptionKind = OptionKind.CALL
    payout: Decimal = field(default_factory=lambda: Decimal("1"))
    settlement_type: SettlementType = SettlementType.CASH


# ---------------------------------------------------------------------------
# FX
# ---------------------------------------------------------------------------


@dataclass
@register_instrument_class(AssetClass.FX, InstrumentClass.SPOT)
class CurrencyPair(Instrument):
    """FX spot pair (``EUR/USD``, ``USD/JPY``, …)."""

    base_currency: Currency = field(default_factory=lambda: currency_of("EUR"))
    quote_currency: Currency = field(default_factory=lambda: currency_of("USD"))
    pip_size: Decimal = field(default_factory=lambda: Decimal("0.0001"))
    contract_size: Decimal = field(default_factory=lambda: Decimal("100000"))

    @classmethod
    def product(cls) -> Product | None:
        return Product.FOREX


# ---------------------------------------------------------------------------
# CFD / Commodity / Synthetic
# ---------------------------------------------------------------------------


@dataclass
@register_instrument_class(AssetClass.EQUITY, InstrumentClass.CFD)
class Cfd(Instrument):
    """Contract-for-difference wrapper around a reference instrument."""

    underlying: str | None = None
    contract_size: Decimal = field(default_factory=lambda: Decimal("1"))
    margin_rate: Decimal | None = None
    financing_rate: Decimal | None = None

    @classmethod
    def product(cls) -> Product | None:
        return Product.CFD


@dataclass
@register_instrument_class(AssetClass.COMMODITY, InstrumentClass.SPOT)
class Commodity(Instrument):
    """Physical commodity (WTI, Brent, gold, wheat, …)."""

    grade: str | None = None
    unit_of_measure: str | None = None  # barrel, troy_ounce, bushel, MMBtu, …
    delivery: str | None = None


@dataclass
@register_instrument_class(AssetClass.MIXED, InstrumentClass.SYNTHETIC)
class SyntheticInstrument(Instrument):
    """Formula-defined synthetic (basket, ratio, pair)."""

    legs: list[InstrumentId] = field(default_factory=list)
    formula: str | None = None
    leg_weights: dict[str, Decimal] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Crypto family
# ---------------------------------------------------------------------------


@dataclass
@register_instrument_class(AssetClass.CRYPTO, InstrumentClass.CRYPTO_TOKEN)
class CryptoToken(Instrument):
    """On-chain token (ERC-20, SPL, BEP-20, …)."""

    chain: str | None = None
    contract_address: str | None = None
    decimals: int = 18
    token_symbol: str | None = None
    is_native: bool = False
    cmc_id: int | None = None
    coingecko_id: str | None = None

    @classmethod
    def product(cls) -> Product | None:
        return Product.CRYPTO


@dataclass
@register_instrument_class(AssetClass.CRYPTO, InstrumentClass.FUTURE)
class CryptoFuture(Instrument):
    """Dated crypto futures contract."""

    underlying: str | None = None
    settlement_currency: Currency = field(default_factory=lambda: currency_of("USDT"))
    expiry: datetime | None = None
    contract_size: Decimal = field(default_factory=lambda: Decimal("1"))
    settlement_type: SettlementType = SettlementType.CASH

    @classmethod
    def product(cls) -> Product | None:
        return Product.FUTURES


@dataclass
@register_instrument_class(AssetClass.CRYPTO, InstrumentClass.PERPETUAL)
class CryptoPerpetual(Instrument):
    """Perpetual futures contract (no expiry, funding rate)."""

    underlying: str | None = None
    settlement_currency: Currency = field(default_factory=lambda: currency_of("USDT"))
    contract_size: Decimal = field(default_factory=lambda: Decimal("1"))
    funding_interval: str | None = "8h"  # e.g. "8h"
    max_leverage: Decimal | None = None
    maker_fee: Decimal | None = None
    taker_fee: Decimal | None = None
    is_inverse: bool = False


@dataclass
@register_instrument_class(AssetClass.CRYPTO, InstrumentClass.OPTION)
class CryptoOption(Instrument):
    """Listed crypto option (Deribit-style)."""

    underlying: str | None = None
    strike: Decimal | None = None
    expiry: datetime | None = None
    kind: OptionKind = OptionKind.CALL
    style: OptionStyle = OptionStyle.EUROPEAN
    settlement_currency: Currency = field(default_factory=lambda: currency_of("USDT"))
    settlement_type: SettlementType = SettlementType.CASH


@dataclass
@register_instrument_class(AssetClass.MIXED, InstrumentClass.PERPETUAL)
class PerpetualContract(Instrument):
    """Generic perpetual contract (cross-class fallback for non-crypto perps)."""

    underlying: str | None = None
    contract_size: Decimal = field(default_factory=lambda: Decimal("1"))
    funding_interval: str | None = "8h"
    margin_currency: Currency = field(default_factory=lambda: currency_of("USD"))


@dataclass
@register_instrument_class(AssetClass.CRYPTO, InstrumentClass.NFT)
class TokenizedAsset(Instrument):
    """Tokenized real-world asset or NFT series."""

    chain: str | None = None
    contract_address: str | None = None
    token_standard: str | None = None  # ERC-721 / ERC-1155 / SPL / ...
    supply: int | None = None
    reference_asset: str | None = None


# ---------------------------------------------------------------------------
# Event / prediction markets
# ---------------------------------------------------------------------------


@dataclass
@register_instrument_class(AssetClass.EVENT, InstrumentClass.BETTING)
class BettingInstrument(Instrument):
    """Sports / prediction market line (Polymarket, Betfair, Kalshi, …)."""

    event_type: str | None = None
    event_name: str | None = None
    event_open: datetime | None = None
    market_id: str | None = None
    market_name: str | None = None
    market_type: str | None = None
    market_start: datetime | None = None
    selection_id: str | None = None
    selection_name: str | None = None
    selection_handicap: Decimal | None = None
    competition: str | None = None
    country_code: str | None = None

    @classmethod
    def product(cls) -> Product | None:
        return Product.BETTING


# ---------------------------------------------------------------------------
# Rates / swaps (for future expansion)
# ---------------------------------------------------------------------------


@dataclass
class Swap(Instrument):
    """Plain-vanilla interest-rate/credit/equity swap placeholder.

    Full gs-quant IRSwap/EqSwap modelling is deferred; this gives us a seat
    for future expansion and satisfies the ``InstrumentClass.SWAP`` slot.
    """

    tenor: str | None = None
    pay_receive: PayReceive = PayReceive.PAY
    pay_leg: dict[str, Any] = field(default_factory=dict)
    receive_leg: dict[str, Any] = field(default_factory=dict)
    fixed_rate: Decimal | None = None
    floating_rate_index: str | None = None
    notional: Decimal | None = None
    effective_date: dateType | None = None
    termination_date: dateType | None = None

    @classmethod
    def product(cls) -> Product | None:
        return Product.SWAP


register_instrument_class(AssetClass.RATES, InstrumentClass.SWAP)(Swap)
