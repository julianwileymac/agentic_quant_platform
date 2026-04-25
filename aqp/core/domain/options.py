"""Options chain primitives.

Complements :mod:`aqp.core.domain.greeks` and
:class:`aqp.core.domain.instrument.OptionContract` with the descriptors used
to publish and query live option chains.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as dateType, datetime
from decimal import Decimal

from aqp.core.domain.greeks import OptionGreekValues
from aqp.core.domain.identifiers import InstrumentId
from aqp.core.domain.instrument import OptionContract


@dataclass(frozen=True)
class OptionSeriesId:
    """Identifier for a chain series ``(underlying, expiry)``.

    Implementations typically mint a stable string from
    ``{underlying}-{expiry.isoformat()}`` so resolvers can address "the 2026-06
    AAPL series" without listing every strike individually.
    """

    underlying: str
    expiry: dateType

    @property
    def value(self) -> str:
        return f"{self.underlying}-{self.expiry.isoformat()}"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class StrikeRange:
    """Inclusive strike range used when slicing a chain."""

    low: Decimal
    high: Decimal

    def contains(self, strike: Decimal) -> bool:
        return self.low <= strike <= self.high


@dataclass
class OptionChainSlice:
    """One strike × one expiry quote + greeks snapshot."""

    instrument_id: InstrumentId
    series: OptionSeriesId
    strike: Decimal
    expiry: dateType
    kind: str  # "call" | "put"
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    volume: Decimal | None = None
    open_interest: Decimal | None = None
    implied_volatility: Decimal | None = None
    greeks: OptionGreekValues | None = None
    ts_event: datetime = field(default_factory=datetime.utcnow)

    @property
    def mid(self) -> Decimal | None:
        if self.bid is None or self.ask is None:
            return None
        return (self.bid + self.ask) / 2


@dataclass
class OptionChain:
    """Full chain (every strike × every kind) for an underlying + expiry."""

    underlying: str
    expiry: dateType
    contracts: list[OptionContract] = field(default_factory=list)
    slices: list[OptionChainSlice] = field(default_factory=list)
    underlying_price: Decimal | None = None
    ts_event: datetime = field(default_factory=datetime.utcnow)

    @property
    def strikes(self) -> list[Decimal]:
        return sorted({s.strike for s in self.slices})

    @property
    def calls(self) -> list[OptionChainSlice]:
        return [s for s in self.slices if s.kind.lower() == "call"]

    @property
    def puts(self) -> list[OptionChainSlice]:
        return [s for s in self.slices if s.kind.lower() == "put"]

    def slice_at(self, strike: Decimal, kind: str) -> OptionChainSlice | None:
        wanted = kind.lower()
        for s in self.slices:
            if s.strike == strike and s.kind.lower() == wanted:
                return s
        return None
