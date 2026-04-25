"""Alpaca broker adapter tests.

Skipped when ``alpaca-py`` is not installed. The tests use a pytest
``monkeypatch`` on the Alpaca ``TradingClient`` so nothing leaves the
process — VCR cassettes are only useful when recording against real
paper endpoints during development.
"""
from __future__ import annotations

import importlib.util
from typing import Any

import pytest

_has_alpaca = importlib.util.find_spec("alpaca") is not None
pytestmark = pytest.mark.skipif(
    not _has_alpaca, reason="alpaca-py not installed (pip install -e '.[alpaca]')"
)


class _FakeAlpacaAccount:
    account_number = "ACC"
    cash = 100000.0
    equity = 100000.0
    initial_margin = 0.0
    currency = "USD"


class _FakeAlpacaOrder:
    def __init__(self) -> None:
        self.id = "abc-123"
        self.symbol = "AAPL"
        self.side = "buy"
        self.status = "new"
        self.order_type = "market"
        self.qty = 10
        self.limit_price = None
        self.stop_price = None
        self.filled_qty = 0
        self.filled_avg_price = 0
        self.submitted_at = None
        self.updated_at = None


class _FakeClient:
    def __init__(self, *_a: Any, **_k: Any) -> None:
        self.submitted: list[Any] = []

    def get_account(self) -> _FakeAlpacaAccount:
        return _FakeAlpacaAccount()

    def submit_order(self, req: Any) -> _FakeAlpacaOrder:
        self.submitted.append(req)
        return _FakeAlpacaOrder()

    def cancel_order_by_id(self, _id: str) -> None:
        return None

    def get_all_positions(self) -> list[Any]:
        return []


@pytest.mark.asyncio
async def test_alpaca_submit_order(monkeypatch: pytest.MonkeyPatch) -> None:
    # The broker accepts explicit api_key/secret_key kwargs so we don't need
    # to rebuild the Settings singleton — just pass creds directly below.
    import aqp.trading.brokerages.alpaca as alpaca_mod
    from aqp.core.types import OrderRequest, OrderSide, OrderType, Symbol

    monkeypatch.setattr(alpaca_mod, "TradingClient", _FakeClient)

    class _FakeStream:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        def subscribe_trade_updates(self, *_a: Any, **_k: Any) -> None:
            return None

        async def _run_forever(self) -> None:  # noqa: SLF001
            return None

        async def stop_ws(self) -> None:
            return None

    monkeypatch.setattr(alpaca_mod, "TradingStream", _FakeStream)

    broker = alpaca_mod.AlpacaBrokerage(api_key="unit-key", secret_key="unit-secret", paper=True)
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
        assert order.order_id == "abc-123"
        acct = await broker.query_account_async()
        assert acct.account_id == "ACC"
    finally:
        await broker.disconnect_async()
