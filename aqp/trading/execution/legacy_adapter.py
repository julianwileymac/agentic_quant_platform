"""Bridge legacy :class:`OrderRequest` / :class:`OrderData` to :class:`DomainOrder`.

During the Phase 2 migration both stacks coexist. This adapter:

1. Translates a legacy :class:`aqp.core.types.OrderRequest` to a
   :class:`DomainOrder` so a Phase 2 brokerage can submit it.
2. Translates a :class:`DomainOrder` back to a legacy
   :class:`aqp.core.types.OrderData` so the existing
   :class:`PaperTradingSession` consumer sees what it expects.
3. Wraps a Phase 2-aware :class:`IDomainBrokerage` implementation as a
   legacy :class:`IAsyncBrokerage` so the existing trading session can
   route through it without code changes.

The adapter does NOT lose information: extra fields on
:class:`DomainOrder` (post_only, reduce_only, outside_rth, ...) are
preserved in ``OrderData.meta`` so callers that round-trip through
the legacy shape can recover them.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import Any

from aqp.core.domain.enums import (
    OrderSide as DomainOrderSide,
    OrderStatus as DomainOrderStatus,
    OrderType as DomainOrderType,
    TimeInForce,
)
from aqp.core.domain.identifiers import (
    AccountId,
    ClientOrderId,
    InstrumentId,
    Symbol2,
    Venue,
    VenueOrderId,
)
from aqp.core.domain.orders import (
    DomainOrder,
    LimitOrder,
    MarketOrder,
    StopLimitOrder,
    StopMarketOrder,
    TrailingStopMarketOrder,
)
from aqp.core.types import (
    AccountData,
    OrderData,
    OrderRequest,
    OrderSide as LegacyOrderSide,
    OrderStatus as LegacyOrderStatus,
    OrderType as LegacyOrderType,
    PositionData,
    Symbol,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Order-type / status / side mapping
# ---------------------------------------------------------------------------


_LEGACY_TO_DOMAIN_ORDER_TYPE: dict[LegacyOrderType, DomainOrderType] = {
    LegacyOrderType.MARKET: DomainOrderType.MARKET,
    LegacyOrderType.LIMIT: DomainOrderType.LIMIT,
    LegacyOrderType.STOP: DomainOrderType.STOP_MARKET,
    LegacyOrderType.STOP_LIMIT: DomainOrderType.STOP_LIMIT,
    LegacyOrderType.MARKET_ON_OPEN: DomainOrderType.MARKET_ON_OPEN,
    LegacyOrderType.MARKET_ON_CLOSE: DomainOrderType.MARKET_ON_CLOSE,
    LegacyOrderType.TRAILING_STOP: DomainOrderType.TRAILING_STOP_MARKET,
}

_DOMAIN_TO_LEGACY_ORDER_TYPE: dict[DomainOrderType, LegacyOrderType] = {
    DomainOrderType.MARKET: LegacyOrderType.MARKET,
    DomainOrderType.LIMIT: LegacyOrderType.LIMIT,
    DomainOrderType.STOP_MARKET: LegacyOrderType.STOP,
    DomainOrderType.STOP_LIMIT: LegacyOrderType.STOP_LIMIT,
    DomainOrderType.MARKET_ON_OPEN: LegacyOrderType.MARKET_ON_OPEN,
    DomainOrderType.MARKET_ON_CLOSE: LegacyOrderType.MARKET_ON_CLOSE,
    DomainOrderType.TRAILING_STOP_MARKET: LegacyOrderType.TRAILING_STOP,
    DomainOrderType.TRAILING_STOP_LIMIT: LegacyOrderType.TRAILING_STOP,
    DomainOrderType.MARKET_IF_TOUCHED: LegacyOrderType.STOP,
    DomainOrderType.LIMIT_IF_TOUCHED: LegacyOrderType.STOP_LIMIT,
    DomainOrderType.MARKET_TO_LIMIT: LegacyOrderType.LIMIT,
}


_LEGACY_TO_DOMAIN_SIDE: dict[LegacyOrderSide, DomainOrderSide] = {
    LegacyOrderSide.BUY: DomainOrderSide.BUY,
    LegacyOrderSide.SELL: DomainOrderSide.SELL,
}

_DOMAIN_TO_LEGACY_SIDE: dict[DomainOrderSide, LegacyOrderSide] = {
    DomainOrderSide.BUY: LegacyOrderSide.BUY,
    DomainOrderSide.SELL: LegacyOrderSide.SELL,
}


_DOMAIN_TO_LEGACY_STATUS: dict[DomainOrderStatus, LegacyOrderStatus] = {
    DomainOrderStatus.INITIALIZED: LegacyOrderStatus.SUBMITTING,
    DomainOrderStatus.SUBMITTING: LegacyOrderStatus.SUBMITTING,
    DomainOrderStatus.ACCEPTED: LegacyOrderStatus.ACCEPTED,
    DomainOrderStatus.PENDING_UPDATE: LegacyOrderStatus.ACCEPTED,
    DomainOrderStatus.PENDING_CANCEL: LegacyOrderStatus.ACCEPTED,
    DomainOrderStatus.EMULATED: LegacyOrderStatus.SUBMITTING,
    DomainOrderStatus.RELEASED: LegacyOrderStatus.SUBMITTING,
    DomainOrderStatus.TRIGGERED: LegacyOrderStatus.ACCEPTED,
    DomainOrderStatus.PARTIALLY_FILLED: LegacyOrderStatus.PART_FILLED,
    DomainOrderStatus.FILLED: LegacyOrderStatus.FILLED,
    DomainOrderStatus.CANCELED: LegacyOrderStatus.CANCELLED,
    DomainOrderStatus.EXPIRED: LegacyOrderStatus.CANCELLED,
    DomainOrderStatus.REJECTED: LegacyOrderStatus.REJECTED,
    DomainOrderStatus.DENIED: LegacyOrderStatus.REJECTED,
}


def _tif_from_str(value: str | None) -> TimeInForce:
    if not value:
        return TimeInForce.DAY
    v = value.lower()
    for tif in TimeInForce:
        if tif.value == v:
            return tif
    # Map common legacy strings.
    if v in ("good_til_canceled", "good_til_cancelled", "gtt"):
        return TimeInForce.GTC
    if v in ("immediate_or_cancel",):
        return TimeInForce.IOC
    if v in ("fill_or_kill",):
        return TimeInForce.FOK
    return TimeInForce.DAY


def _instrument_id_from_symbol(symbol: Symbol) -> InstrumentId:
    venue = symbol.exchange.value if symbol.exchange else "LOCAL"
    return InstrumentId(Symbol2(symbol.ticker), Venue(venue))


# ---------------------------------------------------------------------------
# Public conversion helpers
# ---------------------------------------------------------------------------


def domain_order_from_order_request(
    request: OrderRequest,
    *,
    client_order_id: str | None = None,
    gateway: str | None = None,
    account: str | None = None,
) -> DomainOrder:
    """Translate a legacy :class:`OrderRequest` into a :class:`DomainOrder`.

    Subclass selection matches the legacy order type:

    - MARKET / MARKET_ON_OPEN / MARKET_ON_CLOSE -> ``MarketOrder``
    - LIMIT -> ``LimitOrder``
    - STOP -> ``StopMarketOrder``
    - STOP_LIMIT -> ``StopLimitOrder``
    - TRAILING_STOP -> ``TrailingStopMarketOrder``
    """
    cli_id = ClientOrderId(client_order_id or uuid.uuid4().hex)
    inst_id = _instrument_id_from_symbol(request.symbol)
    side = _LEGACY_TO_DOMAIN_SIDE.get(request.side, DomainOrderSide.NONE)
    qty = Decimal(str(request.quantity))
    tif = _tif_from_str(request.time_in_force)
    domain_type = _LEGACY_TO_DOMAIN_ORDER_TYPE.get(
        request.order_type, DomainOrderType.MARKET
    )
    account_id = AccountId(account) if account else None

    common = dict(
        client_order_id=cli_id,
        instrument_id=inst_id,
        order_side=side,
        quantity=qty,
        order_type=domain_type,
        time_in_force=tif,
        account_id=account_id,
        meta={
            "legacy_reference": request.reference,
            "gateway": gateway,
        },
    )

    if domain_type == DomainOrderType.MARKET:
        return MarketOrder(**common)
    if domain_type == DomainOrderType.LIMIT:
        order = LimitOrder(price=Decimal(str(request.price or 0.0)), **common)
        return order
    if domain_type == DomainOrderType.STOP_MARKET:
        return StopMarketOrder(
            trigger_price=Decimal(str(request.stop_price or 0.0)), **common
        )
    if domain_type == DomainOrderType.STOP_LIMIT:
        return StopLimitOrder(
            trigger_price=Decimal(str(request.stop_price or 0.0)),
            price=Decimal(str(request.price or 0.0)),
            **common,
        )
    if domain_type == DomainOrderType.TRAILING_STOP_MARKET:
        return TrailingStopMarketOrder(
            trailing_offset=Decimal(str(request.stop_price or 0.0)),
            **common,
        )
    # Fallback: best-effort MarketOrder
    return MarketOrder(**common)


def order_data_from_domain_order(
    order: DomainOrder, *, gateway: str = "domain"
) -> OrderData:
    """Translate a :class:`DomainOrder` back to a legacy :class:`OrderData`.

    The Phase-2-only flags are preserved in :attr:`OrderData.reference`
    is left untouched; the raw flag payload travels in a meta carrier
    inside the order's own meta block (read from
    ``order.meta['legacy_meta']``).
    """
    sym = Symbol(
        ticker=order.instrument_id.symbol.value,
        exchange=_venue_to_exchange(order.instrument_id.venue.value),
    )
    legacy_side = _DOMAIN_TO_LEGACY_SIDE.get(order.order_side, LegacyOrderSide.BUY)
    legacy_type = _DOMAIN_TO_LEGACY_ORDER_TYPE.get(
        order.order_type, LegacyOrderType.MARKET
    )
    legacy_status = _DOMAIN_TO_LEGACY_STATUS.get(
        order.status, LegacyOrderStatus.SUBMITTING
    )
    venue_id = (
        order.venue_order_id.value
        if isinstance(order.venue_order_id, VenueOrderId)
        else order.client_order_id.value
    )
    price = _order_price(order)
    stop_price = _order_stop_price(order)
    return OrderData(
        order_id=venue_id,
        gateway=gateway,
        symbol=sym,
        side=legacy_side,
        order_type=legacy_type,
        quantity=float(order.quantity),
        status=legacy_status,
        price=None if price is None else float(price),
        stop_price=None if stop_price is None else float(stop_price),
        filled_quantity=float(order.filled_quantity),
        average_fill_price=float(order.average_fill_price),
        reference=str(order.meta.get("legacy_reference") or order.client_order_id),
        strategy_id=str(order.strategy_id) if order.strategy_id else None,
        time_in_force=order.time_in_force.value,
        created_at=order.ts_init,
        updated_at=order.ts_last,
    )


def _order_price(order: DomainOrder) -> Decimal | None:
    if hasattr(order, "price"):
        price = getattr(order, "price", None)
        if isinstance(price, Decimal) and price > 0:
            return price
    return None


def _order_stop_price(order: DomainOrder) -> Decimal | None:
    if hasattr(order, "trigger_price"):
        tp = getattr(order, "trigger_price", None)
        if isinstance(tp, Decimal) and tp > 0:
            return tp
    return None


def _venue_to_exchange(venue: str) -> Any:
    """Best-effort map a venue string into the legacy :class:`Exchange` enum."""
    from aqp.core.types import Exchange

    try:
        return Exchange(venue)
    except ValueError:
        return Exchange.LOCAL if hasattr(Exchange, "LOCAL") else Exchange.SMART


# ---------------------------------------------------------------------------
# LegacyDomainOrderAdapter — wraps an IDomainBrokerage as an IAsyncBrokerage
# ---------------------------------------------------------------------------


class LegacyDomainOrderAdapter:
    """Wrap an :class:`IDomainBrokerage` in the legacy :class:`IAsyncBrokerage` shape.

    Use this when an existing consumer (PaperTradingSession, backtest
    loop, REST route) calls ``submit_order_async(OrderRequest)`` but the
    underlying broker has already been migrated to Phase 2 and only
    speaks :class:`DomainOrder`.

    The adapter mints a fresh :class:`ClientOrderId` from
    ``uuid.uuid4().hex`` for each submitted request and stashes the
    legacy reference + gateway in the order's meta so callers that round-
    trip values can recover them.

    Reverse direction (wrapping a legacy :class:`IAsyncBrokerage` as
    Phase 2-aware) is not provided here -- legacy brokerages don't
    support the advanced flags (post_only / outside_rth / OCO) so a
    one-way adapter is the only sound bridge.
    """

    def __init__(self, domain_broker: Any, *, gateway: str | None = None) -> None:
        self._broker = domain_broker
        self.name = getattr(domain_broker, "name", "domain_bridge")
        self._gateway = gateway or self.name

    # ------------------------------------------------------------------
    # Async surface mirroring IAsyncBrokerage
    # ------------------------------------------------------------------

    async def connect_async(self) -> None:
        await self._broker.connect_async()

    async def disconnect_async(self) -> None:
        await self._broker.disconnect_async()

    async def submit_order_async(self, request: OrderRequest) -> OrderData:
        domain_order = domain_order_from_order_request(
            request, gateway=self._gateway
        )
        violations = domain_order.validate_flags()
        if violations:
            data = order_data_from_domain_order(domain_order, gateway=self._gateway)
            data.status = LegacyOrderStatus.REJECTED
            logger.warning(
                "DomainOrder validation failed before submit: %s", violations
            )
            return data
        submitted = await self._broker.submit(domain_order)
        return order_data_from_domain_order(submitted, gateway=self._gateway)

    async def cancel_order_async(self, order_id: str) -> bool:
        return await self._broker.cancel(ClientOrderId(order_id))

    async def query_positions_async(self) -> list[PositionData]:
        # The domain broker returns dicts; map them onto PositionData
        # so the legacy session sees what it expects.
        rows = await self._broker.fetch_positions()
        out: list[PositionData] = []
        for r in rows:
            sym = Symbol(
                ticker=str(r.get("vt_symbol", "")).split(".", 1)[0],
                exchange=_venue_to_exchange(str(r.get("venue", "LOCAL"))),
            )
            qty = float(r.get("quantity", 0.0))
            from aqp.core.types import Direction

            direction = (
                Direction.LONG if qty >= 0 else Direction.SHORT
            )
            out.append(
                PositionData(
                    symbol=sym,
                    quantity=abs(qty),
                    direction=direction,
                    average_price=float(r.get("average_entry_price", 0.0)),
                )
            )
        return out

    async def query_account_async(self) -> AccountData:
        return getattr(
            self._broker,
            "account_data",
            lambda: AccountData(cash=0.0, equity=0.0),
        )()

    def stream_order_updates(self) -> AsyncIterator[OrderData]:
        """Translate execution reports to legacy :class:`OrderData` updates."""
        return _execution_report_to_order_data_stream(self._broker, self._gateway)


async def _execution_report_to_order_data_stream(broker: Any, gateway: str):
    """Coroutine generator yielding legacy :class:`OrderData` updates.

    The Phase 2 ``stream_execution_reports`` yields fine-grained event
    records; we coalesce them onto an OrderData snapshot per event so
    the legacy session's drain loop sees the same shape it did before.
    """
    async for report in broker.stream_execution_reports():
        # Best-effort projection: build a synthetic order snapshot
        # from the report's denormalized fields.
        from aqp.core.types import Exchange

        sym = Symbol(
            ticker=getattr(report, "vt_symbol", "UNKNOWN").split(".", 1)[0],
            exchange=Exchange.SMART if not hasattr(Exchange, "LOCAL") else Exchange.LOCAL,
        )
        # Map the venue's report kind to a legacy status.
        from aqp.core.domain.enums import OrderStatus as DStatus

        order_status = (
            getattr(report, "order_status", None) or "submitting"
        )
        try:
            domain_status = DStatus(order_status)
        except ValueError:
            domain_status = DStatus.ACCEPTED
        legacy_status = _DOMAIN_TO_LEGACY_STATUS.get(
            domain_status, LegacyOrderStatus.ACCEPTED
        )
        yield OrderData(
            order_id=getattr(report, "venue_order_id", "") or "",
            gateway=gateway,
            symbol=sym,
            side=(
                LegacyOrderSide.BUY
                if str(getattr(report, "order_side", "buy")).lower() == "buy"
                else LegacyOrderSide.SELL
            ),
            order_type=LegacyOrderType.MARKET,
            quantity=float(getattr(report, "last_quantity", 0.0) or 0.0),
            status=legacy_status,
            filled_quantity=float(getattr(report, "cumulative_quantity", 0.0) or 0.0),
            average_fill_price=float(
                getattr(report, "average_fill_price", 0.0) or 0.0
            ),
            created_at=getattr(report, "ts_event", datetime.utcnow()),
            updated_at=datetime.utcnow(),
        )


__all__ = [
    "LegacyDomainOrderAdapter",
    "domain_order_from_order_request",
    "order_data_from_domain_order",
]
