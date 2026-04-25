"""Typed identifier value objects (nautilus-inspired).

Replaces string-typed ``order_id``/``account_id``/``trader_id`` arguments with
immutable, hashable value objects so the type checker can tell ``OrderId``
apart from ``TradeId`` apart from ``AccountId``. Every ID exposes a ``value``
property and participates in the same ``_Id`` base so equality/hashing/repr
behave uniformly.

On top of the raw IDs we ship an :class:`IdentifierScheme` StrEnum enumerating
every identifier taxonomy AQP understands (tickers, CIK, CUSIP, ISIN, FIGI,
SEDOL, LEI, GVKEY, PermID, OpenFIGI, Bloomberg GID, RIC, FactSet, SIC, NAICS,
GICS, TRBC, ICB, NACE, BICS, GDelt theme, FRED series id, Refinitiv PermID,
Bloomberg parsekyable_des, custom.*). :class:`IdentifierValue` pairs a scheme
with a raw value + optional validity window + provenance; :class:`IdentifierSet`
is an ordered set with O(1) ``by_scheme()`` lookup used by the resolver
pipeline against the ``identifier_links`` table.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


# ---------------------------------------------------------------------------
# Identifier schemes
# ---------------------------------------------------------------------------


class IdentifierScheme(StrEnum):
    """Every identifier taxonomy the platform can store / resolve.

    The ``scheme`` column on ``identifier_links`` uses these values; external
    data sources (SEC EDGAR, OpenFIGI, Refinitiv, Bloomberg, Intrinio, FMP,
    Polygon, AlphaVantage, Benzinga) all fan in through this vocabulary.
    """

    # Market identifiers
    TICKER = "ticker"
    VT_SYMBOL = "vt_symbol"
    BBG_ID = "bbg_id"
    BBG_PARSEKYABLE_DES = "bbg_parsekyable_des"
    RIC = "ric"

    # Global security identifiers
    CUSIP = "cusip"
    ISIN = "isin"
    SEDOL = "sedol"
    FIGI = "figi"
    OPENFIGI = "openfigi"
    WKN = "wkn"
    VALOREN = "valoren"

    # Entity identifiers
    CIK = "cik"
    LEI = "lei"
    GVKEY = "gvkey"
    PERMID = "permid"
    REFINITIV_PERMID = "refinitiv_permid"
    FACTSET_ID = "factset_id"
    DUNS = "duns"
    IRS_EIN = "irs_ein"

    # Economic / alt identifiers
    FRED_SERIES_ID = "fred_series_id"
    BLS_SERIES_ID = "bls_series_id"
    ECB_SERIES_ID = "ecb_series_id"
    GDELT_THEME = "gdelt_theme"
    COT_CODE = "cot_code"

    # Industry classifications (also valid identifiers on an issuer)
    SIC = "sic"
    NAICS = "naics"
    GICS = "gics"
    TRBC = "trbc"
    ICB = "icb"
    NACE = "nace"
    BICS = "bics"

    # Location
    COUNTRY_ISO = "country_iso"

    # DeFi / on-chain
    ERC20_ADDRESS = "erc20_address"
    EVM_CHAIN_ID = "evm_chain_id"

    # Exchange-specific
    IBKR_CONID = "ibkr_conid"
    ALPACA_ASSET_ID = "alpaca_asset_id"
    POLYGON_TICKER = "polygon_ticker"

    # Custom / internal
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# Base ID value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Id:
    """Base class for typed identifier value objects.

    Subclasses inherit immutability, hashability, and a uniform ``from_str``
    constructor. The stored ``value`` is always a string so the same object
    can round-trip through JSON/YAML without a custom encoder.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError(f"{type(self).__name__} value must be non-empty")

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_str(cls, value: str) -> _Id:
        return cls(value)


class Venue(_Id):
    """An execution venue / exchange (``NASDAQ``, ``IDEALPRO``, ``BINANCE``)."""


class Symbol2(_Id):
    """Raw venue-local symbol (``AAPL``, ``BTCUSDT``, ``ES FUT``).

    Named ``Symbol2`` so it can coexist with the legacy
    :class:`aqp.core.types.Symbol` during the migration window. The legacy
    class is being retrofitted to delegate to :class:`InstrumentId`.
    """


class ClientOrderId(_Id):
    """Client-issued order identifier (locally unique)."""


class VenueOrderId(_Id):
    """Venue-assigned order identifier."""


class OrderListId(_Id):
    """Identifier shared across all orders in a contingency list."""


class TradeId(_Id):
    """Execution / fill identifier."""


class PositionId(_Id):
    """Position identifier, stable across fills."""


class AccountId(_Id):
    """Broker account identifier (``IB-DU12345``, ``ALPACA-PAPER-...``)."""


class StrategyId(_Id):
    """Strategy identifier keyed into the ``strategies`` table."""


class TraderId(_Id):
    """Human/automated trader identifier."""


class ComponentId(_Id):
    """Opaque component identifier used by the event bus."""


class ActorId(_Id):
    """Identifier for an engine actor (data feed, risk monitor, ...)."""


class ExecAlgorithmId(_Id):
    """Identifier for an execution algorithm instance."""


class ClientId(_Id):
    """Client (LLM / user / API consumer) identifier."""


# ---------------------------------------------------------------------------
# InstrumentId — composite identifier used as primary key
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InstrumentId:
    """Canonical composite identifier for an instrument.

    Mirrors nautilus_trader's ``InstrumentId(symbol, venue)`` + the legacy
    ``vt_symbol`` scheme used throughout AQP. ``__str__`` returns the
    ``SYMBOL.VENUE`` form (vt_symbol). Parsing is tolerant of missing venue
    and of the older all-caps convention.
    """

    symbol: Symbol2
    venue: Venue

    @property
    def value(self) -> str:
        return f"{self.symbol.value}.{self.venue.value}"

    @property
    def vt_symbol(self) -> str:
        """Back-compat alias for ``value``."""
        return self.value

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_str(cls, vt_symbol: str, default_venue: str = "LOCAL") -> InstrumentId:
        if "." in vt_symbol:
            sym, ven = vt_symbol.rsplit(".", 1)
        else:
            sym, ven = vt_symbol, default_venue
        return cls(Symbol2(sym), Venue(ven))

    @classmethod
    def from_parts(cls, symbol: str, venue: str) -> InstrumentId:
        return cls(Symbol2(symbol), Venue(venue))


# ---------------------------------------------------------------------------
# IdentifierValue + IdentifierSet
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IdentifierValue:
    """One ``(scheme, value)`` triple with optional validity window.

    Mirrors the shape of one row in ``identifier_links`` — callers can
    construct a set of these, flow them through the resolver, and have the
    resolver persist them idempotently.
    """

    scheme: IdentifierScheme
    value: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    confidence: float = 1.0
    source: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def is_active(self, as_of: datetime | None = None) -> bool:
        """Whether this identifier is valid at ``as_of`` (now if omitted)."""
        moment = as_of or datetime.utcnow()
        if self.valid_from and moment < self.valid_from:
            return False
        if self.valid_to and moment > self.valid_to:
            return False
        return True

    def as_dict(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme.value,
            "value": self.value,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "confidence": self.confidence,
            "source": self.source,
            "meta": dict(self.meta),
        }


@dataclass
class IdentifierSet:
    """Ordered container of :class:`IdentifierValue` with fast lookup by scheme.

    Supports forward resolution (``by_scheme(scheme)`` returns every matching
    identifier, or ``primary_of(scheme)`` returns the highest-confidence one),
    reverse lookup (``value_to_schemes(value)``), and conversion to/from the
    ``identifier_links`` row shape.
    """

    values: list[IdentifierValue] = field(default_factory=list)
    _by_scheme: dict[IdentifierScheme, list[IdentifierValue]] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self) -> None:
        self._by_scheme = {}
        for v in self.values:
            self._by_scheme.setdefault(v.scheme, []).append(v)

    def __iter__(self) -> Iterator[IdentifierValue]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)

    def __contains__(self, scheme: IdentifierScheme | str) -> bool:
        key = scheme if isinstance(scheme, IdentifierScheme) else IdentifierScheme(scheme)
        return key in self._by_scheme

    def add(self, identifier: IdentifierValue) -> None:
        self.values.append(identifier)
        self._by_scheme.setdefault(identifier.scheme, []).append(identifier)

    def extend(self, identifiers: Iterable[IdentifierValue]) -> None:
        for i in identifiers:
            self.add(i)

    def by_scheme(self, scheme: IdentifierScheme | str) -> list[IdentifierValue]:
        key = scheme if isinstance(scheme, IdentifierScheme) else IdentifierScheme(scheme)
        return list(self._by_scheme.get(key, []))

    def primary_of(
        self,
        scheme: IdentifierScheme | str,
        *,
        as_of: datetime | None = None,
    ) -> IdentifierValue | None:
        """Highest-confidence identifier of ``scheme`` currently valid at ``as_of``."""
        candidates = [v for v in self.by_scheme(scheme) if v.is_active(as_of)]
        if not candidates:
            return None
        return max(candidates, key=lambda v: v.confidence)

    def value_of(
        self,
        scheme: IdentifierScheme | str,
        *,
        as_of: datetime | None = None,
    ) -> str | None:
        identifier = self.primary_of(scheme, as_of=as_of)
        return identifier.value if identifier else None

    def value_to_schemes(self, raw_value: str) -> list[IdentifierScheme]:
        """Reverse lookup: what schemes does this raw value appear under?"""
        return [v.scheme for v in self.values if v.value == raw_value]

    def as_list(self) -> list[dict[str, Any]]:
        return [v.as_dict() for v in self.values]

    @classmethod
    def from_list(cls, rows: Iterable[dict[str, Any]]) -> IdentifierSet:
        items: list[IdentifierValue] = []
        for row in rows:
            scheme_raw = row.get("scheme")
            value = row.get("value")
            if scheme_raw is None or value is None:
                continue
            scheme = IdentifierScheme(scheme_raw) if isinstance(scheme_raw, str) else scheme_raw
            items.append(
                IdentifierValue(
                    scheme=scheme,
                    value=str(value),
                    valid_from=_parse_ts(row.get("valid_from")),
                    valid_to=_parse_ts(row.get("valid_to")),
                    confidence=float(row.get("confidence") or 1.0),
                    source=row.get("source"),
                    meta=dict(row.get("meta") or {}),
                )
            )
        return cls(values=items)

    def merge(self, other: IdentifierSet) -> IdentifierSet:
        """Return a new set combining ``self`` + ``other`` without duplicates."""
        seen: set[tuple[IdentifierScheme, str]] = set()
        merged: list[IdentifierValue] = []
        for source in (self, other):
            for v in source:
                key = (v.scheme, v.value)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(v)
        return IdentifierSet(values=merged)


def _parse_ts(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        return None
