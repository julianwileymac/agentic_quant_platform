"""Simulated brokerage with slippage + commission.

Implements :class:`IBrokerage` so it plugs into the same code path as a
future paper/live adapter (Lean pattern).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from aqp.core.interfaces import IBrokerage
from aqp.core.types import (
    AccountData,
    Direction,
    OrderData,
    OrderRequest,
    OrderSide,
    OrderStatus,
    PositionData,
    TradeData,
)


class SimulatedBrokerage(IBrokerage):
    """Fills market orders at the next bar's open with linear slippage."""

    name = "sim"

    def __init__(
        self,
        initial_cash: float = 100000.0,
        commission_pct: float = 0.0005,
        slippage_bps: float = 2.0,
    ) -> None:
        self.cash = float(initial_cash)
        self.commission_pct = float(commission_pct)
        self.slippage_bps = float(slippage_bps)
        self.equity = float(initial_cash)
        self.positions: dict[str, PositionData] = {}
        self.orders: dict[str, OrderData] = {}
        self.trades: list[TradeData] = []
        self.account_id = f"sim-{uuid.uuid4().hex[:6]}"

    # --- IBrokerage ----
    def connect(self) -> None:
        return

    def disconnect(self) -> None:
        return

    def submit_order(self, request: OrderRequest) -> OrderData:
        order = request.create_order(order_id=uuid.uuid4().hex[:12], gateway=self.name)
        order.status = OrderStatus.NEW
        self.orders[order.order_id] = order
        return order

    def cancel_order(self, order_id: str) -> bool:
        order = self.orders.get(order_id)
        if not order or not order.is_active():
            return False
        order.status = OrderStatus.CANCELLED
        return True

    def query_positions(self) -> list[PositionData]:
        return list(self.positions.values())

    def query_account(self) -> AccountData:
        return AccountData(
            account_id=self.account_id,
            cash=self.cash,
            equity=self.equity,
            margin_used=0.0,
        )

    # --- Simulator mechanics ----
    def fill_open_orders(self, fill_price_map: dict[str, float], timestamp: datetime) -> list[TradeData]:
        """Fill all active orders at the provided per-symbol prices.

        Adds slippage in the side-direction (buys fill worse, sells fill worse).
        Records the resulting ``TradeData`` and mutates position + cash state.
        """
        fills: list[TradeData] = []
        for order in list(self.orders.values()):
            if not order.is_active():
                continue
            base_price = fill_price_map.get(order.symbol.vt_symbol)
            if base_price is None or base_price <= 0:
                order.status = OrderStatus.REJECTED
                continue
            slip = base_price * (self.slippage_bps / 10000.0)
            fill_price = base_price + slip if order.side == OrderSide.BUY else base_price - slip
            trade = self._apply_fill(order, fill_price, timestamp)
            fills.append(trade)
        return fills

    def _apply_fill(self, order: OrderData, fill_price: float, timestamp: datetime) -> TradeData:
        qty = order.quantity
        notional = qty * fill_price
        commission = notional * self.commission_pct
        slippage_cost = abs(fill_price - (order.price or fill_price)) * qty

        sym_key = order.symbol.vt_symbol
        pos = self.positions.get(sym_key)

        if order.side == OrderSide.BUY:
            self.cash -= notional + commission
            if pos is None:
                self.positions[sym_key] = PositionData(
                    symbol=order.symbol,
                    direction=Direction.LONG,
                    quantity=qty,
                    average_price=fill_price,
                )
            else:
                if pos.direction == Direction.SHORT:
                    matched = min(pos.quantity, qty)
                    realized = (pos.average_price - fill_price) * matched
                    pos.realized_pnl += realized
                    pos.quantity -= matched
                    remaining_buy = qty - matched
                    if pos.quantity <= 0 and remaining_buy > 0:
                        self.positions[sym_key] = PositionData(
                            symbol=order.symbol,
                            direction=Direction.LONG,
                            quantity=remaining_buy,
                            average_price=fill_price,
                            realized_pnl=pos.realized_pnl,
                        )
                    elif pos.quantity <= 0:
                        self.positions.pop(sym_key, None)
                else:
                    new_qty = pos.quantity + qty
                    pos.average_price = (pos.average_price * pos.quantity + fill_price * qty) / new_qty
                    pos.quantity = new_qty
        else:  # SELL
            self.cash += notional - commission
            if pos is None:
                self.positions[sym_key] = PositionData(
                    symbol=order.symbol,
                    direction=Direction.SHORT,
                    quantity=qty,
                    average_price=fill_price,
                )
            else:
                if pos.direction == Direction.LONG:
                    matched = min(pos.quantity, qty)
                    realized = (fill_price - pos.average_price) * matched
                    pos.realized_pnl += realized
                    pos.quantity -= matched
                    remaining_sell = qty - matched
                    if pos.quantity <= 0 and remaining_sell > 0:
                        self.positions[sym_key] = PositionData(
                            symbol=order.symbol,
                            direction=Direction.SHORT,
                            quantity=remaining_sell,
                            average_price=fill_price,
                            realized_pnl=pos.realized_pnl,
                        )
                    elif pos.quantity <= 0:
                        self.positions.pop(sym_key, None)
                else:
                    new_qty = pos.quantity + qty
                    pos.average_price = (pos.average_price * pos.quantity + fill_price * qty) / new_qty
                    pos.quantity = new_qty

        order.filled_quantity = qty
        order.average_fill_price = fill_price
        order.status = OrderStatus.FILLED
        order.updated_at = timestamp

        trade = TradeData(
            trade_id=uuid.uuid4().hex[:12],
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            price=fill_price,
            quantity=qty,
            timestamp=timestamp,
            commission=commission,
            slippage=slippage_cost,
            strategy_id=order.strategy_id,
        )
        self.trades.append(trade)
        return trade

    def mark_to_market(self, prices: dict[str, float]) -> float:
        notional = 0.0
        for key, pos in self.positions.items():
            mark = prices.get(key, pos.average_price)
            sign = 1.0 if pos.direction != Direction.SHORT else -1.0
            notional += sign * pos.quantity * mark
            pos.unrealized_pnl = (mark - pos.average_price) * pos.quantity * sign
        self.equity = self.cash + notional
        return self.equity
