"""Interactive Brokers adapter using ``ib-async``.

Requires a running TWS or IB Gateway and the ``ibkr`` extra::

    pip install -e ".[ibkr]"

Default ports: 7497 = paper, 7496 = live. Populate via ``AQP_IBKR_PORT``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

try:
    from ib_async import IB  # type: ignore[import]
    from ib_async import LimitOrder as _IBLimit
    from ib_async import MarketOrder as _IBMarket
    from ib_async import Stock as _IBStock
    from ib_async import StopLimitOrder as _IBStopLimit
    from ib_async import StopOrder as _IBStop
except ImportError as exc:  # pragma: no cover — optional
    raise ImportError(
        'InteractiveBrokersBrokerage requires the "ibkr" extra. '
        'Install with: pip install -e ".[ibkr]"'
    ) from exc

from aqp.config import settings
from aqp.core.registry import register
from aqp.core.types import (
    AccountData,
    Direction,
    OrderData,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionData,
    Symbol,
)
from aqp.trading.brokerages.base import BaseAsyncBrokerage, traced_broker_call

logger = logging.getLogger(__name__)


_IB_STATUS_MAP: dict[str, OrderStatus] = {
    "PendingSubmit": OrderStatus.SUBMITTING,
    "PendingCancel": OrderStatus.SUBMITTING,
    "PreSubmitted": OrderStatus.SUBMITTING,
    "Submitted": OrderStatus.NEW,
    "ApiPending": OrderStatus.SUBMITTING,
    "Inactive": OrderStatus.REJECTED,
    "Cancelled": OrderStatus.CANCELLED,
    "ApiCancelled": OrderStatus.CANCELLED,
    "Filled": OrderStatus.FILLED,
    "PartiallyFilled": OrderStatus.PARTIAL,
}


@register("InteractiveBrokersBrokerage")
class InteractiveBrokersBrokerage(BaseAsyncBrokerage):
    """IBKR adapter supporting stocks (extensible to futures/options)."""

    name = "ibkr"
    rate_limit_per_second = 2.0  # IB pacing guideline

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
        exchange: str = "SMART",
        currency: str = "USD",
        connect_timeout: float = 8.0,
        readonly: bool = False,
    ) -> None:
        super().__init__()
        self.host = host or settings.ibkr_host
        self.port = int(port if port is not None else settings.ibkr_port)
        self.client_id = int(client_id if client_id is not None else settings.ibkr_client_id)
        self.exchange = exchange
        self.currency = currency
        self.connect_timeout = float(connect_timeout)
        self.readonly = bool(readonly)
        self._ib = IB()
        self._ib.orderStatusEvent += self._on_order_status

    async def _connect_impl(self) -> None:
        """Open the gateway socket with an explicit timeout.

        We deliberately **do not** call ``ib_async.util.patchAsyncio()``
        here — that helper monkey-patches asyncio via
        ``nest_asyncio.apply()`` so you can run ``asyncio.run`` from inside
        an already-running Jupyter loop. FastAPI/uvicorn already supplies
        a proper asyncio loop; calling ``patchAsyncio()`` inside a
        worker corrupts ``anyio``'s backend detection on Python 3.14 and
        every subsequent sync FastAPI route 500s with
        ``anyio.NoEventLoopError``. See ``tests/test_brokers_route.py``
        for the regression guard.
        """
        try:
            await self._ib.connectAsync(
                self.host,
                self.port,
                clientId=self.client_id,
                timeout=self.connect_timeout,
                readonly=self.readonly,
            )
        except (asyncio.TimeoutError, ConnectionError, OSError) as exc:
            raise ConnectionError(
                f"IB Gateway at {self.host}:{self.port} not reachable "
                f"(clientId={self.client_id}): {exc}. "
                "Verify the gateway is running, the API is enabled, and "
                "no other client is already using this clientId."
            ) from exc

    async def _disconnect_impl(self) -> None:
        try:
            self._ib.disconnect()
        except Exception:
            logger.exception("ibkr disconnect error")

    @traced_broker_call("broker.submit_order", venue="ibkr")
    async def _submit_order_impl(self, request: OrderRequest) -> OrderData:
        contract = _IBStock(request.symbol.ticker, self.exchange, self.currency)
        action = "BUY" if request.side == OrderSide.BUY else "SELL"
        ib_order = self._to_ib_order(request, action)
        trade = self._ib.placeOrder(contract, ib_order)
        await asyncio.sleep(0)  # yield so IB processes the request
        return _ib_trade_to_aqp(trade, request.symbol)

    @traced_broker_call("broker.cancel_order", venue="ibkr")
    async def _cancel_order_impl(self, order_id: str) -> bool:
        # Prefer ``reqAllOpenOrdersAsync`` over the sync ``openTrades()`` —
        # the sync variant internally calls ``util.run`` which breaks
        # inside a running asyncio loop once we dropped ``patchAsyncio``.
        open_trades = await self._open_trades_async()
        for open_trade in open_trades:
            if str(open_trade.order.orderId) == str(order_id):
                self._ib.cancelOrder(open_trade.order)
                return True
        return False

    @traced_broker_call("broker.query_positions", venue="ibkr")
    async def _query_positions_impl(self) -> list[PositionData]:
        rows = await self._positions_async()
        return [_ib_position_to_aqp(r) for r in rows]

    @traced_broker_call("broker.query_account", venue="ibkr")
    async def _query_account_impl(self) -> AccountData:
        # The sync ``accountSummary()`` wraps ``accountSummaryAsync()`` in
        # ``util.run`` which can't run inside an already-running loop —
        # award the same fate as cancel / positions above and await the
        # async variant directly.
        rows = await self._account_summary_async()
        summary = {s.tag: s for s in rows}

        def _f(key: str, default: float = 0.0) -> float:
            item = summary.get(key)
            try:
                return float(item.value) if item else default
            except (TypeError, ValueError):
                return default

        account_id = summary["AccountCode"].account if "AccountCode" in summary else "ibkr"
        return AccountData(
            account_id=account_id,
            cash=_f("TotalCashValue"),
            equity=_f("NetLiquidation"),
            margin_used=_f("MaintMarginReq"),
            currency=self.currency,
            updated_at=datetime.utcnow(),
        )

    # Async variant trampolines — kept as separate methods so tests can
    # monkeypatch just the network call without touching the metric/tracing
    # decorators on the public _impl methods above.

    async def _account_summary_async(self) -> list[Any]:
        return await self._ib.accountSummaryAsync()

    async def _positions_async(self) -> list[Any]:
        # ib_async does not expose a named coroutine for positions; call
        # the same request primitive the sync method would and await it.
        return list(await self._ib.reqPositionsAsync())

    async def _open_trades_async(self) -> list[Any]:
        # ``reqAllOpenOrdersAsync`` refreshes the internal order book; the
        # adapter then reads ``trades()`` which is a pure accessor (no
        # event loop side effects).
        await self._ib.reqAllOpenOrdersAsync()
        return list(self._ib.trades())

    # ----------------------------- helpers ------------------------------

    def _to_ib_order(self, request: OrderRequest, action: str) -> Any:
        qty = request.quantity
        if request.order_type == OrderType.LIMIT:
            return _IBLimit(action, qty, request.price or 0.0)
        if request.order_type == OrderType.STOP:
            return _IBStop(action, qty, request.stop_price or 0.0)
        if request.order_type == OrderType.STOP_LIMIT:
            return _IBStopLimit(action, qty, request.price or 0.0, request.stop_price or 0.0)
        return _IBMarket(action, qty)

    def _on_order_status(self, trade: Any) -> None:
        try:
            order = _ib_trade_to_aqp(trade)
            asyncio.get_event_loop().call_soon_threadsafe(
                self._order_event_queue.put_nowait, order
            )
        except Exception:
            logger.exception("could not translate IB order status event")


def _ib_trade_to_aqp(trade: Any, symbol_hint: Symbol | None = None) -> OrderData:
    ib_order = trade.order
    status_name = getattr(trade.orderStatus, "status", "Submitted")
    status = _IB_STATUS_MAP.get(status_name, OrderStatus.NEW)
    side = OrderSide.BUY if ib_order.action == "BUY" else OrderSide.SELL
    order_type_mapping = {
        "MKT": OrderType.MARKET,
        "LMT": OrderType.LIMIT,
        "STP": OrderType.STOP,
        "STP LMT": OrderType.STOP_LIMIT,
    }
    order_type = order_type_mapping.get(ib_order.orderType, OrderType.MARKET)
    symbol = symbol_hint or Symbol(ticker=str(trade.contract.symbol))
    return OrderData(
        order_id=str(ib_order.orderId),
        gateway="ibkr",
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=float(ib_order.totalQuantity),
        status=status,
        price=float(getattr(ib_order, "lmtPrice", 0.0) or 0.0) or None,
        stop_price=float(getattr(ib_order, "auxPrice", 0.0) or 0.0) or None,
        filled_quantity=float(getattr(trade.orderStatus, "filled", 0.0) or 0.0),
        average_fill_price=float(getattr(trade.orderStatus, "avgFillPrice", 0.0) or 0.0),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def _ib_position_to_aqp(row: Any) -> PositionData:
    qty = float(row.position)
    return PositionData(
        symbol=Symbol(ticker=str(row.contract.symbol)),
        direction=Direction.LONG if qty >= 0 else Direction.SHORT,
        quantity=abs(qty),
        average_price=float(row.avgCost),
    )
