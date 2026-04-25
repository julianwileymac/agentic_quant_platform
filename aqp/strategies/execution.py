"""Execution models (Lean stage 5) — convert portfolio targets into orders."""
from __future__ import annotations

import math
from typing import Any

from aqp.core.interfaces import IExecutionModel
from aqp.core.registry import register
from aqp.core.types import (
    Direction,
    OrderRequest,
    OrderSide,
    OrderType,
    PortfolioTarget,
    PositionData,
)


def _current_weight(
    symbol_key: str,
    positions: dict[str, PositionData],
    equity: float,
    price: float,
) -> float:
    pos = positions.get(symbol_key)
    if not pos or equity <= 0 or price <= 0:
        return 0.0
    sign = 1 if pos.direction != Direction.SHORT else -1
    return sign * pos.quantity * price / equity


@register("MarketOrderExecution")
class MarketOrderExecution(IExecutionModel):
    """Immediate market orders sized from (target - current) × equity / price."""

    def __init__(self, min_order_value: float = 10.0, round_lot: int = 1) -> None:
        self.min_order_value = float(min_order_value)
        self.round_lot = int(round_lot)

    def execute(
        self, targets: list[PortfolioTarget], context: dict[str, Any]
    ) -> list[OrderRequest]:
        equity = float(context.get("equity", 0.0))
        prices: dict[str, float] = context.get("prices", {}) or {}
        positions: dict[str, PositionData] = context.get("positions", {}) or {}
        strategy_id = context.get("strategy_id")

        orders: list[OrderRequest] = []
        target_keys = {t.symbol.vt_symbol for t in targets}

        # --- open / rebalance targets ----
        for t in targets:
            key = t.symbol.vt_symbol
            price = prices.get(key)
            if price is None or price <= 0:
                continue
            current = _current_weight(key, positions, equity, price)
            delta_w = t.target_weight - current
            notional = delta_w * equity
            if abs(notional) < self.min_order_value:
                continue
            qty_raw = notional / price
            qty = math.floor(abs(qty_raw) / self.round_lot) * self.round_lot
            if qty <= 0:
                continue
            side = OrderSide.BUY if qty_raw > 0 else OrderSide.SELL
            orders.append(
                OrderRequest(
                    symbol=t.symbol,
                    side=side,
                    order_type=OrderType.MARKET,
                    quantity=float(qty),
                    price=price,
                    reference=f"rebalance:{strategy_id}:{key}",
                    strategy_id=strategy_id,
                )
            )

        # --- close positions not in target ----
        for key, pos in positions.items():
            if key in target_keys or pos.quantity <= 0:
                continue
            side = OrderSide.SELL if pos.direction != Direction.SHORT else OrderSide.BUY
            price = prices.get(key, pos.average_price)
            orders.append(
                OrderRequest(
                    symbol=pos.symbol,
                    side=side,
                    order_type=OrderType.MARKET,
                    quantity=float(pos.quantity),
                    price=price,
                    reference=f"exit:{strategy_id}:{key}",
                    strategy_id=strategy_id,
                )
            )
        return orders
