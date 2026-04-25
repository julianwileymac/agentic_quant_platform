"""Alpaca broker adapter.

Requires the ``alpaca`` optional extra::

    pip install -e ".[alpaca]"

Supports paper or live accounts; which is chosen by ``paper=True/False`` or
``settings.alpaca_paper`` when unset.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

try:
    from alpaca.trading.client import TradingClient  # type: ignore[import]
    from alpaca.trading.enums import (  # type: ignore[import]
        OrderSide as _AlpacaOrderSide,
    )
    from alpaca.trading.enums import (
        OrderStatus as _AlpacaStatus,
    )
    from alpaca.trading.enums import (
        TimeInForce,
    )
    from alpaca.trading.requests import (  # type: ignore[import]
        LimitOrderRequest,
        MarketOrderRequest,
        StopLimitOrderRequest,
        StopOrderRequest,
    )
    from alpaca.trading.stream import TradingStream  # type: ignore[import]
except ImportError as exc:  # pragma: no cover — optional
    raise ImportError(
        'AlpacaBrokerage requires the "alpaca" extra. '
        'Install with: pip install -e ".[alpaca]"'
    ) from exc

import contextlib

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


_STATUS_MAP: dict[str, OrderStatus] = {
    _AlpacaStatus.NEW.value: OrderStatus.NEW,
    _AlpacaStatus.ACCEPTED.value: OrderStatus.NEW,
    _AlpacaStatus.PARTIALLY_FILLED.value: OrderStatus.PARTIAL,
    _AlpacaStatus.FILLED.value: OrderStatus.FILLED,
    _AlpacaStatus.CANCELED.value: OrderStatus.CANCELLED,
    _AlpacaStatus.EXPIRED.value: OrderStatus.CANCELLED,
    _AlpacaStatus.REJECTED.value: OrderStatus.REJECTED,
    _AlpacaStatus.PENDING_NEW.value: OrderStatus.SUBMITTING,
    _AlpacaStatus.PENDING_CANCEL.value: OrderStatus.SUBMITTING,
    _AlpacaStatus.DONE_FOR_DAY.value: OrderStatus.CANCELLED,
}


class _RetryableAlpacaError(Exception):
    """Used by tenacity to classify retryable transient errors."""


@register("AlpacaBrokerage")
class AlpacaBrokerage(BaseAsyncBrokerage):
    """Trade-side adapter for Alpaca (equities + crypto)."""

    name = "alpaca"
    rate_limit_per_second = 3.0  # Alpaca default is 200/min ≈ 3.3/s

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        paper: bool | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__()
        self.api_key = api_key or settings.alpaca_api_key
        self.secret_key = secret_key or settings.alpaca_secret_key
        self.paper = settings.alpaca_paper if paper is None else bool(paper)
        self.base_url = base_url or settings.alpaca_base_url or None
        if not (self.api_key and self.secret_key):
            raise ValueError(
                "Alpaca credentials missing; set AQP_ALPACA_API_KEY and AQP_ALPACA_SECRET_KEY"
            )
        self._client: TradingClient | None = None
        self._stream: TradingStream | None = None
        self._stream_task: asyncio.Task[None] | None = None

    # ---------------------------- lifecycle ------------------------------

    async def _connect_impl(self) -> None:
        self._client = TradingClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=self.paper,
            url_override=self.base_url,
        )
        # Touch the account endpoint so connection failures surface early.
        await asyncio.to_thread(self._client.get_account)
        self._start_stream()

    async def _disconnect_impl(self) -> None:
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._stream_task
        self._stream = None
        self._client = None

    def _start_stream(self) -> None:
        if self._stream is not None:
            return
        self._stream = TradingStream(self.api_key, self.secret_key, paper=self.paper)
        self._stream.subscribe_trade_updates(self._handle_trade_update)
        self._stream_task = asyncio.create_task(self._stream._run_forever())  # noqa: SLF001

    async def _handle_trade_update(self, data: Any) -> None:
        try:
            order = _alpaca_order_to_aqp(data.order)
            await self._order_event_queue.put(order)
        except Exception:
            logger.exception("malformed Alpaca trade update")

    # ---------------------------- ops -----------------------------------

    @traced_broker_call("broker.submit_order", venue="alpaca")
    @retry(
        wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(_RetryableAlpacaError),
        reraise=True,
    )
    async def _submit_order_impl(self, request: OrderRequest) -> OrderData:
        assert self._client is not None, "call connect_async() first"
        alpaca_req = self._to_alpaca_request(request)
        try:
            placed = await asyncio.to_thread(self._client.submit_order, alpaca_req)
        except Exception as exc:  # noqa: BLE001
            if _is_transient(exc):
                raise _RetryableAlpacaError(str(exc)) from exc
            raise
        return _alpaca_order_to_aqp(placed, symbol_hint=request.symbol)

    @traced_broker_call("broker.cancel_order", venue="alpaca")
    async def _cancel_order_impl(self, order_id: str) -> bool:
        assert self._client is not None
        try:
            await asyncio.to_thread(self._client.cancel_order_by_id, order_id)
        except Exception:
            logger.exception("alpaca cancel failed")
            return False
        return True

    @traced_broker_call("broker.query_positions", venue="alpaca")
    async def _query_positions_impl(self) -> list[PositionData]:
        assert self._client is not None
        rows = await asyncio.to_thread(self._client.get_all_positions)
        return [_alpaca_position_to_aqp(r) for r in rows]

    @traced_broker_call("broker.query_account", venue="alpaca")
    async def _query_account_impl(self) -> AccountData:
        assert self._client is not None
        acct = await asyncio.to_thread(self._client.get_account)
        return AccountData(
            account_id=str(acct.account_number),
            cash=float(acct.cash),
            equity=float(acct.equity),
            margin_used=float(getattr(acct, "initial_margin", 0.0) or 0.0),
            currency=getattr(acct, "currency", "USD"),
            updated_at=datetime.utcnow(),
        )

    # ---------------------------- mapping helpers -----------------------

    def _to_alpaca_request(self, request: OrderRequest) -> Any:
        side = (
            _AlpacaOrderSide.BUY if request.side == OrderSide.BUY else _AlpacaOrderSide.SELL
        )
        tif = TimeInForce.DAY
        common = dict(
            symbol=request.symbol.ticker,
            qty=request.quantity,
            side=side,
            time_in_force=tif,
        )
        if request.order_type == OrderType.LIMIT:
            return LimitOrderRequest(limit_price=request.price, **common)
        if request.order_type == OrderType.STOP:
            return StopOrderRequest(stop_price=request.stop_price, **common)
        if request.order_type == OrderType.STOP_LIMIT:
            return StopLimitOrderRequest(
                stop_price=request.stop_price,
                limit_price=request.price,
                **common,
            )
        return MarketOrderRequest(**common)


def _alpaca_order_to_aqp(placed: Any, symbol_hint: Symbol | None = None) -> OrderData:
    side = OrderSide.BUY if str(placed.side).lower().endswith("buy") else OrderSide.SELL
    status_raw = getattr(placed, "status", None)
    status = _STATUS_MAP.get(str(status_raw), OrderStatus.NEW)
    order_type_str = str(getattr(placed, "order_type", "market")).lower()
    try:
        order_type = OrderType(order_type_str)
    except ValueError:
        order_type = OrderType.MARKET
    symbol = symbol_hint or Symbol(ticker=str(placed.symbol))
    price_value = getattr(placed, "limit_price", None)
    return OrderData(
        order_id=str(placed.id),
        gateway="alpaca",
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=float(placed.qty),
        status=status,
        price=float(price_value) if price_value is not None else None,
        stop_price=float(getattr(placed, "stop_price", None) or 0.0) or None,
        filled_quantity=float(getattr(placed, "filled_qty", 0.0) or 0.0),
        average_fill_price=float(getattr(placed, "filled_avg_price", 0.0) or 0.0),
        created_at=getattr(placed, "submitted_at", datetime.utcnow()) or datetime.utcnow(),
        updated_at=getattr(placed, "updated_at", datetime.utcnow()) or datetime.utcnow(),
    )


def _alpaca_position_to_aqp(row: Any) -> PositionData:
    qty = float(row.qty)
    direction = Direction.LONG if qty >= 0 else Direction.SHORT
    return PositionData(
        symbol=Symbol(ticker=str(row.symbol)),
        direction=direction,
        quantity=abs(qty),
        average_price=float(row.avg_entry_price),
        unrealized_pnl=float(getattr(row, "unrealized_pl", 0.0) or 0.0),
        realized_pnl=float(getattr(row, "realized_pl", 0.0) or 0.0),
    )


def _is_transient(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        tag in msg
        for tag in ("timeout", "temporarily unavailable", "429", "502", "503", "504")
    )
