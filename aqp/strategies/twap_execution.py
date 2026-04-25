"""TWAP execution model — even-sized slices across a horizon."""
from __future__ import annotations

import uuid
from typing import Any

from aqp.core.interfaces import IExecutionModel
from aqp.core.registry import register
from aqp.core.types import OrderRequest, OrderSide, OrderType, PortfolioTarget


@register("TwapExecution")
class TwapExecution(IExecutionModel):
    """Time-weighted average price slicer.

    Sends an equal-sized child order each bar until the delta is
    exhausted (``horizon_bars`` slices).
    """

    def __init__(self, horizon_bars: int = 5, min_order_value: float = 50.0) -> None:
        self.horizon_bars = max(1, int(horizon_bars))
        self.min_order_value = float(min_order_value)

    def execute(self, targets: list[PortfolioTarget], context: dict[str, Any]) -> list[OrderRequest]:
        equity = float(context.get("equity", 0.0))
        positions = context.get("positions") or {}
        if isinstance(positions, list):
            positions = {p.symbol.vt_symbol: p for p in positions}
        prices = context.get("prices") or {}
        strategy_id = context.get("strategy_id")
        orders: list[OrderRequest] = []
        for target in targets:
            vt_symbol = target.symbol.vt_symbol
            price = float(prices.get(vt_symbol, 0.0))
            if price <= 0 or equity <= 0:
                continue
            pos = positions.get(vt_symbol)
            current_qty = float(pos.quantity) if pos else 0.0
            desired_qty = (target.target_weight * equity) / price
            delta = desired_qty - current_qty
            slice_qty = delta / self.horizon_bars
            slice_notional = abs(slice_qty) * price
            if slice_notional < self.min_order_value:
                continue
            side = OrderSide.BUY if slice_qty > 0 else OrderSide.SELL
            orders.append(
                OrderRequest(
                    symbol=target.symbol,
                    side=side,
                    order_type=OrderType.MARKET,
                    quantity=abs(slice_qty),
                    price=None,
                    reference=f"twap:{uuid.uuid4().hex[:6]}",
                    strategy_id=strategy_id,
                )
            )
        return orders
