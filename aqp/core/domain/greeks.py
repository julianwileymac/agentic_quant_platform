"""Options greeks value objects.

Small, allocation-cheap containers for per-contract, per-position, and
portfolio-level sensitivities. The numerical pricing logic itself lives
under :mod:`aqp.ml` / strategy code — these are pure data shapes intended to
flow through the event bus, persistence layer, and UI grids unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from aqp.core.domain.identifiers import InstrumentId


@dataclass
class OptionGreekValues:
    """Per-contract greeks at a single point in time."""

    delta: Decimal = Decimal("0")
    gamma: Decimal = Decimal("0")
    theta: Decimal = Decimal("0")
    vega: Decimal = Decimal("0")
    rho: Decimal = Decimal("0")
    vanna: Decimal | None = None
    volga: Decimal | None = None
    charm: Decimal | None = None
    speed: Decimal | None = None
    zomma: Decimal | None = None
    color: Decimal | None = None
    iv: Decimal | None = None


@dataclass
class OptionGreeks:
    """Per-contract greek snapshot keyed to an instrument + timestamp."""

    instrument_id: InstrumentId
    ts_event: datetime
    values: OptionGreekValues = field(default_factory=OptionGreekValues)
    underlying_price: Decimal | None = None
    implied_volatility: Decimal | None = None
    time_to_expiry_years: Decimal | None = None
    risk_free_rate: Decimal | None = None
    dividend_yield: Decimal | None = None


@dataclass
class BlackScholesResult:
    """Full pricing payload returned by a Black-Scholes solver."""

    instrument_id: InstrumentId
    ts_event: datetime
    theoretical_price: Decimal
    greeks: OptionGreekValues
    implied_volatility: Decimal | None = None
    solver: str = "black_scholes"


@dataclass
class PortfolioGreeks:
    """Aggregated book-level greek exposure."""

    ts_event: datetime
    delta: Decimal = Decimal("0")
    gamma: Decimal = Decimal("0")
    theta: Decimal = Decimal("0")
    vega: Decimal = Decimal("0")
    rho: Decimal = Decimal("0")
    dollar_delta: Decimal | None = None
    dollar_gamma: Decimal | None = None
    dex: Decimal | None = None  # delta dollars (DEX)
    gex: Decimal | None = None  # gamma exposure
    breakdown: dict[str, OptionGreekValues] = field(default_factory=dict)
