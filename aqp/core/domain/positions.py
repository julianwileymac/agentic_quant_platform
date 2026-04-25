"""Position hierarchy + position-event family.

Complements :mod:`aqp.core.domain.orders` with the position lifecycle.
``DomainPosition`` is the generic base; concrete subclasses
(:class:`EquityPosition`, :class:`FuturesPosition`, :class:`OptionPosition`)
add asset-class-specific accounting (e.g. futures carry margin/multiplier,
options carry greeks/strike/expiry).

Every state change emits an event so the :mod:`aqp.persistence.ledger` can
rebuild a position's history from the event stream.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from aqp.core.domain.enums import PositionSide
from aqp.core.domain.greeks import OptionGreekValues
from aqp.core.domain.identifiers import (
    AccountId,
    InstrumentId,
    PositionId,
    StrategyId,
    TraderId,
)
from aqp.core.domain.money import Money


# ---------------------------------------------------------------------------
# Position base
# ---------------------------------------------------------------------------


@dataclass
class DomainPosition:
    """Base position record.

    Named ``DomainPosition`` to coexist with the legacy
    :class:`aqp.core.types.PositionData`. The legacy class is retrofitted to
    delegate to this; new code should prefer these richer types.
    """

    position_id: PositionId
    instrument_id: InstrumentId
    side: PositionSide

    quantity: Decimal = Decimal("0")
    average_open_price: Decimal = Decimal("0")
    average_close_price: Decimal = Decimal("0")

    realized_pnl: Money | None = None
    unrealized_pnl: Money | None = None
    commission: Money | None = None

    opened_ts: datetime | None = None
    last_ts: datetime | None = None
    closed_ts: datetime | None = None

    account_id: AccountId | None = None
    strategy_id: StrategyId | None = None
    trader_id: TraderId | None = None

    tags: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.closed_ts is None and self.quantity != 0

    @property
    def is_closed(self) -> bool:
        return self.closed_ts is not None

    @property
    def is_flat(self) -> bool:
        return self.quantity == 0

    @property
    def notional(self) -> Decimal:
        return self.quantity * self.average_open_price


@dataclass
class EquityPosition(DomainPosition):
    """Long/short cash equity position."""

    dividends_received: Money | None = None
    short_interest_paid: Money | None = None


@dataclass
class FuturesPosition(DomainPosition):
    """Futures position with margin + multiplier."""

    multiplier: Decimal = Decimal("1")
    margin_initial: Money | None = None
    margin_maintenance: Money | None = None


@dataclass
class OptionPosition(DomainPosition):
    """Option leg with greeks."""

    multiplier: Decimal = Decimal("100")
    strike: Decimal | None = None
    expiry: datetime | None = None
    greeks: OptionGreekValues | None = None


# ---------------------------------------------------------------------------
# Position events
# ---------------------------------------------------------------------------


@dataclass
class _PositionEventBase:
    """Shared fields on every position event."""

    position_id: PositionId
    instrument_id: InstrumentId
    ts_event: datetime = field(default_factory=datetime.utcnow)
    ts_init: datetime | None = None
    event_id: str | None = None
    account_id: AccountId | None = None
    strategy_id: StrategyId | None = None
    trader_id: TraderId | None = None


@dataclass
class PositionOpened(_PositionEventBase):
    side: PositionSide = PositionSide.LONG
    quantity: Decimal = Decimal("0")
    price: Decimal = Decimal("0")


@dataclass
class PositionChanged(_PositionEventBase):
    side: PositionSide = PositionSide.LONG
    quantity: Decimal = Decimal("0")
    average_price: Decimal = Decimal("0")
    last_qty: Decimal = Decimal("0")
    last_px: Decimal = Decimal("0")
    realized_pnl: Money | None = None
    unrealized_pnl: Money | None = None


@dataclass
class PositionClosed(_PositionEventBase):
    side: PositionSide = PositionSide.FLAT
    realized_pnl: Money | None = None
    duration_seconds: float | None = None


@dataclass
class PositionAdjusted(_PositionEventBase):
    reason: str | None = None
    adjustment_qty: Decimal = Decimal("0")
    new_quantity: Decimal = Decimal("0")


@dataclass
class PositionSnapshot(_PositionEventBase):
    quantity: Decimal = Decimal("0")
    average_open_price: Decimal = Decimal("0")
    unrealized_pnl: Money | None = None
    realized_pnl: Money | None = None
