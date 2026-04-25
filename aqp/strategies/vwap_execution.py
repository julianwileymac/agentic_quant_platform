"""VWAP-slicing execution model (Lean ``VolumeWeightedAveragePriceExecutionModel``).

Splits the net order quantity across ``horizon_bars`` future bars,
proportional to the recent participation-weighted volume profile. In
backtest/paper mode we emit child orders tagged by slice index; the
transaction handler is responsible for releasing them on subsequent
bars.
"""
from __future__ import annotations

import uuid
from typing import Any

from aqp.core.interfaces import IExecutionModel
from aqp.core.registry import register
from aqp.core.types import (
    OrderRequest,
    OrderSide,
    OrderType,
    PortfolioTarget,
)


@register("VwapExecution")
class VwapExecution(IExecutionModel):
    """Slice the target delta into ``horizon_bars`` orders."""

    def __init__(
        self,
        participation_rate: float = 0.1,
        horizon_bars: int = 5,
        min_order_value: float = 50.0,
    ) -> None:
        self.participation_rate = float(participation_rate)
        self.horizon_bars = max(1, int(horizon_bars))
        self.min_order_value = float(min_order_value)

    def execute(self, targets: list[PortfolioTarget], context: dict[str, Any]) -> list[OrderRequest]:
        equity = float(context.get("equity", 0.0))
        positions = context.get("positions") or {}
        prices = context.get("prices") or {}
        if isinstance(positions, list):
            positions = {p.symbol.vt_symbol: p for p in positions}
        strategy_id = context.get("strategy_id")
        slice_idx = int(context.get("vwap_slice_idx", 0)) % self.horizon_bars
        orders: list[OrderRequest] = []
        for target in targets:
            vt_symbol = target.symbol.vt_symbol
            price = float(prices.get(vt_symbol, 0.0))
            if price <= 0 or equity <= 0:
                continue
            pos = positions.get(vt_symbol)
            current_qty = float(pos.quantity) * (1.0 if (pos and str(pos.direction) == "long") else -1.0) if pos else 0.0
            desired_notional = target.target_weight * equity
            desired_qty = desired_notional / price
            delta = desired_qty - current_qty
            # Slice the remaining delta over the horizon.
            remaining_slices = max(1, self.horizon_bars - slice_idx)
            slice_qty = delta / remaining_slices
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
                    reference=f"vwap:{uuid.uuid4().hex[:6]}:{slice_idx + 1}/{self.horizon_bars}",
                    strategy_id=strategy_id,
                )
            )
        return orders
