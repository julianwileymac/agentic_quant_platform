"""REST brokerage (Tradier) tests using pytest-httpx."""
from __future__ import annotations

import importlib.util

import pytest

_has_pytest_httpx = importlib.util.find_spec("pytest_httpx") is not None
pytestmark = pytest.mark.skipif(
    not _has_pytest_httpx, reason="pytest-httpx not installed"
)


@pytest.mark.asyncio
@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
async def test_tradier_submit_and_query(httpx_mock) -> None:
    from aqp.core.types import OrderRequest, OrderSide, OrderType, Symbol
    from aqp.trading.brokerages.tradier import TradierBrokerage

    base = "https://sandbox.tradier.com/v1"
    httpx_mock.add_response(
        url=f"{base}/accounts/ACC123/balances",
        json={
            "balances": {
                "account_number": "ACC123",
                "total_cash": 100000.0,
                "total_equity": 100000.0,
            }
        },
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=f"{base}/accounts/ACC123/orders",
        method="POST",
        json={"order": {"id": "42", "status": "ok", "symbol": "AAPL", "quantity": 10}},
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=f"{base}/accounts/ACC123/orders",
        method="GET",
        json={"orders": {"order": [{"id": "42", "status": "filled", "symbol": "AAPL", "quantity": 10}]}},
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=f"{base}/accounts/ACC123/orders/42",
        method="DELETE",
        json={"ok": True},
        is_reusable=True,
    )

    broker = TradierBrokerage(
        token="dummy",
        account_id="ACC123",
        base_url=base,
    )
    # Raise the poll interval so the background task doesn't race with teardown.
    broker.order_poll_interval_seconds = 60.0
    await broker.connect_async()
    try:
        order = await broker.submit_order_async(
            OrderRequest(
                symbol=Symbol(ticker="AAPL"),
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=10,
            )
        )
        assert order.order_id == "42"
        ok = await broker.cancel_order_async("42")
        assert ok is True
    finally:
        await broker.disconnect_async()
