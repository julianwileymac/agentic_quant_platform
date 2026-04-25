"""Tradier REST broker adapter (sandbox + production).

Tradier uses simple bearer-token auth and form-encoded POSTs. Full docs:
https://documentation.tradier.com
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

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
from aqp.trading.brokerages.rest import RestBrokerage

logger = logging.getLogger(__name__)


_STATUS_MAP: dict[str, OrderStatus] = {
    "open": OrderStatus.NEW,
    "pending": OrderStatus.SUBMITTING,
    "submitted": OrderStatus.NEW,
    "accepted": OrderStatus.NEW,
    "partially_filled": OrderStatus.PARTIAL,
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "expired": OrderStatus.CANCELLED,
    "rejected": OrderStatus.REJECTED,
    "error": OrderStatus.REJECTED,
}


@register("TradierBrokerage")
class TradierBrokerage(RestBrokerage):
    """Tradier REST adapter (equities). Extend _order_payload for options."""

    name = "tradier"
    base_url = "https://sandbox.tradier.com/v1"

    def __init__(
        self,
        token: str | None = None,
        account_id: str | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(
            token=token or settings.tradier_token,
            base_url=base_url or settings.tradier_base_url,
            account_id=account_id or settings.tradier_account_id,
        )
        if not self.account_id:
            raise ValueError(
                "TradierBrokerage requires an account id "
                "(set AQP_TRADIER_ACCOUNT_ID or pass account_id=...)"
            )

    def _send_form_encoded(self) -> bool:
        return True

    def _orders_path(self) -> str:
        return f"/accounts/{self.account_id}/orders"

    def _order_detail_path(self, order_id: str) -> str:
        return f"/accounts/{self.account_id}/orders/{order_id}"

    def _positions_path(self) -> str:
        return f"/accounts/{self.account_id}/positions"

    def _account_path(self) -> str:
        return f"/accounts/{self.account_id}/balances"

    # -------------------------------- order payload ----------------------

    def _order_payload(self, request: OrderRequest) -> dict[str, Any]:
        order_type_map = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP: "stop",
            OrderType.STOP_LIMIT: "stop_limit",
        }
        side_map = {
            OrderSide.BUY: "buy",
            OrderSide.SELL: "sell",
        }
        payload: dict[str, Any] = {
            "class": "equity",
            "symbol": request.symbol.ticker,
            "side": side_map[request.side],
            "quantity": int(request.quantity),
            "type": order_type_map[request.order_type],
            "duration": "day",
        }
        if request.price is not None:
            payload["price"] = f"{request.price:.2f}"
        if request.stop_price is not None:
            payload["stop"] = f"{request.stop_price:.2f}"
        return payload

    # -------------------------------- parsers ----------------------------

    def _parse_order(self, raw: Any, *, request: OrderRequest | None = None) -> OrderData:
        order = raw.get("order", raw) if isinstance(raw, dict) else raw
        status = _STATUS_MAP.get(str(order.get("status", "open")).lower(), OrderStatus.NEW)
        side = OrderSide.BUY if order.get("side", "buy").startswith("buy") else OrderSide.SELL
        order_type_str = str(order.get("type", "market")).lower()
        try:
            order_type = OrderType(order_type_str)
        except ValueError:
            order_type = OrderType.MARKET
        symbol = Symbol(ticker=str(order.get("symbol", request.symbol.ticker if request else "?")))
        return OrderData(
            order_id=str(order.get("id")),
            gateway="tradier",
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=float(order.get("quantity", 0.0)),
            status=status,
            price=(float(order["price"]) if order.get("price") else None),
            stop_price=(float(order["stop"]) if order.get("stop") else None),
            filled_quantity=float(order.get("exec_quantity", 0.0) or 0.0),
            average_fill_price=float(order.get("avg_fill_price", 0.0) or 0.0),
            created_at=self._utcnow(),
            updated_at=self._utcnow(),
        )

    def _parse_orders(self, raw: Any) -> list[OrderData]:
        if not isinstance(raw, dict):
            return []
        orders_block = raw.get("orders") or {}
        if not isinstance(orders_block, dict):
            return []
        items = orders_block.get("order")
        if items is None:
            return []
        if isinstance(items, dict):
            items = [items]
        return [self._parse_order({"order": it}) for it in items]

    def _parse_positions(self, raw: Any) -> list[PositionData]:
        positions_block = raw.get("positions") if isinstance(raw, dict) else {}
        if not isinstance(positions_block, dict):
            return []
        items = positions_block.get("position")
        if items is None:
            return []
        if isinstance(items, dict):
            items = [items]
        out: list[PositionData] = []
        for p in items:
            qty = float(p.get("quantity", 0.0))
            if qty == 0:
                continue
            out.append(
                PositionData(
                    symbol=Symbol(ticker=str(p.get("symbol"))),
                    direction=Direction.LONG if qty > 0 else Direction.SHORT,
                    quantity=abs(qty),
                    average_price=float(p.get("cost_basis", 0.0)) / abs(qty) if qty else 0.0,
                )
            )
        return out

    def _parse_account(self, raw: Any) -> AccountData:
        balances = raw.get("balances", {}) if isinstance(raw, dict) else {}
        return AccountData(
            account_id=str(balances.get("account_number", self.account_id)),
            cash=float(balances.get("total_cash", 0.0) or 0.0),
            equity=float(balances.get("total_equity", 0.0) or 0.0),
            margin_used=float(balances.get("margin", {}).get("stock_short_value", 0.0) or 0.0) if isinstance(balances.get("margin"), dict) else 0.0,
            currency="USD",
            updated_at=datetime.now(tz=UTC).replace(tzinfo=None),
        )
