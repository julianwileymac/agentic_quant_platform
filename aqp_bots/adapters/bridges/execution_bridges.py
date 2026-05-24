"""Execution-adapter bridges over existing AQP brokerage code.

The kernel runtime drives orders through :class:`ExecutionAdapter`. The
existing AQP code drives them through :class:`aqp.trading.execution.protocol.IDomainBrokerage`
(`AlpacaBrokerage`, `InteractiveBrokersBrokerage`) and through
:class:`aqp.trading.session.PaperTradingSession`. These bridge classes
let kernel-mode bots reach those same backends without rewriting them.

Translation contract:

- :class:`aqp_bots.schemas.NewOrder` -> :class:`aqp.core.types.OrderData`
- :class:`aqp.core.types.TradeData` -> :class:`aqp_bots.schemas.Fill`

The bridges live behind lazy imports so this module can be imported
without pulling in the entire AQP trading stack (helpful for the
operator pod which only needs the adapter metadata).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

from aqp_bots.adapters.protocol import (
    AdapterCapability,
    AdapterUnavailable,
    ExecutionAdapter,
)
from aqp_bots.schemas.trading import (
    Fill,
    NewOrder,
    OrderAck,
    OrderRef,
    OrderStatus,
    Position,
    ReconcileSnapshot,
    Reject,
    Side,
)

logger = logging.getLogger(__name__)


class _BridgeBase(ExecutionAdapter):
    """Shared plumbing for AQP-brokerage-backed bridges."""

    __abstract_adapter__ = True

    def __init__(self) -> None:
        self._brokerage: Any | None = None
        self._stream_queue: asyncio.Queue[OrderAck | Fill | Reject] = asyncio.Queue(maxsize=4096)

    async def connect(self) -> None:
        raise NotImplementedError

    async def place(self, order: NewOrder) -> OrderAck | Reject:
        if self._brokerage is None:
            await self.connect()
        try:
            order_data = self._to_order_data(order)
            ack = await self._brokerage.submit(order_data)  # type: ignore[union-attr]
            if ack is None:
                return Reject(
                    ref=OrderRef(client_order_id=order.client_order_id),
                    reason_code="brokerage_no_ack",
                    reason_text="brokerage returned None",
                )
            return OrderAck(
                ref=OrderRef(
                    client_order_id=order.client_order_id,
                    venue_order_id=getattr(ack, "orderid", "") or "",
                    venue=order.venue,
                    symbol=order.symbol,
                ),
                status=OrderStatus.ACKNOWLEDGED,
                accepted_quantity=Decimal(str(order.quantity)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("bridge place failed")
            return Reject(
                ref=OrderRef(client_order_id=order.client_order_id),
                reason_code="bridge_exception",
                reason_text=str(exc),
            )

    async def cancel(self, ref: OrderRef) -> OrderAck | Reject:
        if self._brokerage is None:
            return Reject(ref=ref, reason_code="not_connected")
        try:
            await self._brokerage.cancel(ref.venue_order_id or ref.client_order_id)  # type: ignore[union-attr]
            return OrderAck(ref=ref, status=OrderStatus.CANCEL_PENDING)
        except Exception as exc:  # noqa: BLE001
            return Reject(ref=ref, reason_code="bridge_exception", reason_text=str(exc))

    async def stream(self) -> AsyncIterator[OrderAck | Fill | Reject]:
        while True:
            evt = await self._stream_queue.get()
            yield evt

    async def positions(self) -> tuple[Position, ...]:
        if self._brokerage is None:
            return ()
        try:
            raw = await self._brokerage.positions()  # type: ignore[union-attr]
            return tuple(self._to_position(p) for p in raw)
        except Exception:  # noqa: BLE001
            logger.debug("bridge positions() failed", exc_info=True)
            return ()

    async def reconcile(self) -> ReconcileSnapshot:
        if self._brokerage is None:
            return ReconcileSnapshot(
                venue=self.adapter_kind, open_orders=(), positions=(), snapshot_ts_ns=0
            )
        try:
            import time

            positions = await self.positions()
            return ReconcileSnapshot(
                venue=self.adapter_kind,
                open_orders=(),
                positions=positions,
                snapshot_ts_ns=time.time_ns(),
            )
        except Exception:  # noqa: BLE001
            return ReconcileSnapshot(
                venue=self.adapter_kind, open_orders=(), positions=(), snapshot_ts_ns=0
            )

    async def aclose(self) -> None:
        if self._brokerage is None:
            return
        try:
            close = getattr(self._brokerage, "aclose", None)
            if callable(close):
                await close()
        except Exception:  # noqa: BLE001
            pass
        self._brokerage = None

    # ------------------------------------------------------------------
    # Translation helpers
    # ------------------------------------------------------------------

    def _to_order_data(self, order: NewOrder) -> Any:
        """Translate :class:`NewOrder` to ``aqp.core.types.OrderData``."""
        from aqp.core.types import OrderData

        return OrderData(
            vt_symbol=order.symbol,
            direction=order.side.value,
            volume=float(order.quantity),
            price=float(order.limit_price) if order.limit_price is not None else 0.0,
            order_type=order.order_type,
            reference=order.client_order_id,
        )

    def _to_position(self, raw: Any) -> Position:
        symbol = getattr(raw, "vt_symbol", None) or getattr(raw, "symbol", "")
        return Position(
            venue=self.adapter_kind,
            symbol=str(symbol),
            qty=Decimal(str(getattr(raw, "quantity", 0))),
            avg_price=Decimal(str(getattr(raw, "average_price", 0) or 0)),
            realized_pnl=Decimal(str(getattr(raw, "realized_pnl", 0) or 0)),
            unrealized_pnl=Decimal(str(getattr(raw, "unrealized_pnl", 0) or 0)),
        )


class PaperBridgeExecutionAdapter(_BridgeBase):
    """Bridge over the existing paper trading session.

    Use this for ``capabilities.frequency in {mid, low, eod}`` bots in
    backtest / paper environments. HFT bots should NOT use this bridge
    because it inherits the legacy paper session's millisecond clock.
    """

    adapter_kind = "paper_bridge"
    adapter_alias = "paper_bridge"
    capability = AdapterCapability(
        venue="paper",
        asset_classes=("equity", "spot_crypto", "future"),
        supports_amend=False,
        supports_oco=False,
        order_types=("market", "limit", "stop", "stop_limit"),
    )

    def __init__(self, *, session_config: dict[str, Any] | None = None) -> None:
        super().__init__()
        self._session_config = session_config or {}

    async def connect(self) -> None:
        try:
            from aqp.trading.runner import build_session_from_config
        except ImportError as exc:
            raise AdapterUnavailable(
                "PaperBridgeExecutionAdapter requires aqp.trading"
            ) from exc
        # The "brokerage" here is the paper session — strategies submit
        # through the session and get fills back through the session bus.
        session = build_session_from_config(self._session_config)
        self._brokerage = session.brokerage


class AlpacaBridgeExecutionAdapter(_BridgeBase):
    """Bridge over the existing :class:`AlpacaBrokerage`."""

    adapter_kind = "alpaca_bridge"
    adapter_alias = "alpaca_bridge"
    capability = AdapterCapability(
        venue="alpaca",
        asset_classes=("equity", "spot_crypto"),
        supports_amend=True,
        supports_oco=True,
        order_types=("market", "limit", "stop", "stop_limit"),
    )

    def __init__(self, *, paper: bool = True) -> None:
        super().__init__()
        self._paper = paper

    async def connect(self) -> None:
        try:
            from aqp.trading.brokerages.alpaca import AlpacaBrokerage
        except ImportError as exc:
            raise AdapterUnavailable("AlpacaBrokerage unavailable") from exc
        self._brokerage = AlpacaBrokerage(paper=self._paper)
        if hasattr(self._brokerage, "connect"):
            await self._brokerage.connect()


class IBKRBridgeExecutionAdapter(_BridgeBase):
    """Bridge over the existing :class:`InteractiveBrokersBrokerage`."""

    adapter_kind = "ibkr_bridge"
    adapter_alias = "ibkr_bridge"
    capability = AdapterCapability(
        venue="ibkr",
        asset_classes=("equity", "future", "option", "fx"),
        supports_amend=True,
        supports_oco=True,
        order_types=("market", "limit", "stop", "stop_limit"),
    )

    async def connect(self) -> None:
        try:
            from aqp.trading.brokerages.ibkr import InteractiveBrokersBrokerage
        except ImportError as exc:
            raise AdapterUnavailable("InteractiveBrokersBrokerage unavailable") from exc
        self._brokerage = InteractiveBrokersBrokerage()
        if hasattr(self._brokerage, "connect"):
            await self._brokerage.connect()


__all__ = [
    "AlpacaBridgeExecutionAdapter",
    "IBKRBridgeExecutionAdapter",
    "PaperBridgeExecutionAdapter",
]
