"""IBKR broker adapter tests.

Skipped when ``ib-async`` isn't installed or when no IB Gateway is
reachable at localhost. The happy path uses a ``monkeypatch`` around
``ib_async.IB`` so we never open a real socket.
"""
from __future__ import annotations

import importlib.util
import socket
from typing import Any

import pytest

_has_ib = importlib.util.find_spec("ib_async") is not None


def _has_ibkr_gateway(host: str = "127.0.0.1", port: int = 7497, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _has_ib,
    reason="ib-async not installed (pip install -e '.[ibkr]')",
)


@pytest.mark.asyncio
async def test_ibkr_adapter_translates_orders(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use a fake ``IB`` object to verify translation without hitting Gateway."""
    import aqp.trading.brokerages.ibkr as ibkr_mod
    from aqp.core.types import OrderRequest, OrderSide, OrderType, Symbol

    class _Event:
        def __init__(self) -> None:
            self._handlers: list[Any] = []

        def __iadd__(self, fn: Any):
            self._handlers.append(fn)
            return self

    class _FakeTrade:
        def __init__(self, contract: Any, order: Any) -> None:
            self.contract = contract
            self.order = order

            class _Status:
                status = "Submitted"
                filled = 0
                avgFillPrice = 0.0

            self.orderStatus = _Status()

    class _FakeIB:
        def __init__(self) -> None:
            self.orderStatusEvent = _Event()
            self._connected = True

        async def connectAsync(self, *_a: Any, **_k: Any) -> None:
            return None

        def disconnect(self) -> None:
            self._connected = False

        def isConnected(self) -> bool:
            return self._connected

        def placeOrder(self, contract: Any, order: Any) -> _FakeTrade:
            order.orderId = 99
            order.orderType = "MKT"
            order.action = "BUY"
            order.totalQuantity = 5
            order.lmtPrice = 0.0
            order.auxPrice = 0.0
            return _FakeTrade(contract, order)

        def openTrades(self) -> list[Any]:
            return []

        def positions(self) -> list[Any]:
            return []

        def accountSummary(self) -> list[Any]:
            return []

    monkeypatch.setattr(ibkr_mod, "IB", _FakeIB)
    # Note: we no longer need to stub ``ib_util`` — the adapter stopped
    # importing it after the Python-3.14 ``patchAsyncio`` incident that
    # broke ``anyio.to_thread.run_sync``.

    broker = ibkr_mod.InteractiveBrokersBrokerage(host="127.0.0.1", port=4001, client_id=9)
    await broker.connect_async()
    try:
        order = await broker.submit_order_async(
            OrderRequest(
                symbol=Symbol(ticker="AAPL"),
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=5,
            )
        )
        assert order.order_id == "99"
        assert order.side.value == "buy"
    finally:
        await broker.disconnect_async()
