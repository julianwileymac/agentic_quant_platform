"""Event-driven backtest engine — next-bar fill simulation at bar open.

High-fidelity enough for research while staying pure-Python and fast on a
laptop. The engine drives a :class:`IStrategy` through a chronological
replay of bars, routing orders through :class:`SimulatedBrokerage`.

The engine supports **both** the legacy ``IStrategy.on_bar(bar, ctx)``
and the new Lean-style ``on_data(slice, ctx)`` entry points — strategies
that implement ``on_data`` receive a single :class:`Slice` per timestamp
instead of one ``BarData`` per symbol. Every placed order surfaces as an
:class:`OrderTicket` with a populated :class:`OrderEvent` stream so
downstream result handlers and the UI ledger can reconstruct the full
order lifecycle.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.backtest.broker_sim import SimulatedBrokerage
from aqp.backtest.interrupts import (
    InterruptHandler,
    InterruptRequest,
    InterruptResolution,
    NullInterruptHandler,
    find_first_matching_rule,
)
from aqp.backtest.metrics import summarise
from aqp.core.interfaces import IStrategy
from aqp.core.registry import register
from aqp.core.slice import Slice
from aqp.core.types import (
    BarData,
    Interval,
    OrderEvent,
    OrderRequest,
    OrderTicket,
    Symbol,
    TradeData,
)

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: pd.DataFrame
    orders: pd.DataFrame
    signals: pd.DataFrame = field(default_factory=pd.DataFrame)
    tickets: list[OrderTicket] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    start: datetime | None = None
    end: datetime | None = None
    initial_cash: float = 0.0
    final_equity: float = 0.0


@register("EventDrivenBacktester")
class EventDrivenBacktester:
    """Chronologically replays bars and executes orders at next bar's open."""

    def __init__(
        self,
        initial_cash: float = 100000.0,
        commission_pct: float = 0.0005,
        slippage_bps: float = 2.0,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        interrupt_rules: list[dict[str, Any]] | None = None,
        interrupt_handler: InterruptHandler | None = None,
    ) -> None:
        self.initial_cash = float(initial_cash)
        self.commission_pct = float(commission_pct)
        self.slippage_bps = float(slippage_bps)
        self.start = pd.Timestamp(start) if start else None
        self.end = pd.Timestamp(end) if end else None
        self.interrupt_rules: list[dict[str, Any]] = list(interrupt_rules or [])
        self.interrupt_handler: InterruptHandler = (
            interrupt_handler or NullInterruptHandler()
        )

    def _request_to_dict(self, request: OrderRequest) -> dict[str, Any]:
        return {
            "vt_symbol": request.symbol.vt_symbol if request.symbol else None,
            "side": request.side.value if hasattr(request.side, "value") else str(request.side),
            "order_type": (
                request.order_type.value
                if hasattr(request.order_type, "value")
                else str(request.order_type)
            ),
            "quantity": float(request.quantity),
            "price": float(request.price) if request.price is not None else None,
            "stop_price": float(request.stop_price) if request.stop_price is not None else None,
            "reference": request.reference,
            "strategy_id": request.strategy_id,
            "time_in_force": request.time_in_force,
        }

    @staticmethod
    def _coerce_enum(enum_cls: type, value: Any, fallback: Any) -> Any:
        """Coerce a string into ``enum_cls`` accepting both upper and lower case."""
        if value is None:
            return fallback
        if isinstance(value, enum_cls):
            return value
        s = str(value).strip()
        for candidate in (s, s.lower(), s.upper()):
            try:
                return enum_cls(candidate)
            except (ValueError, KeyError):
                continue
        return fallback

    def _replacement_to_request(
        self,
        original: OrderRequest,
        replacement: dict[str, Any],
    ) -> OrderRequest | None:
        try:
            from aqp.core.types import OrderSide, OrderType

            new = OrderRequest(
                symbol=original.symbol,
                side=self._coerce_enum(
                    OrderSide, replacement.get("side"), original.side
                ),
                order_type=self._coerce_enum(
                    OrderType, replacement.get("order_type"), original.order_type
                ),
                quantity=float(replacement.get("quantity", original.quantity)),
                price=replacement.get("price", original.price),
                stop_price=replacement.get("stop_price", original.stop_price),
                reference=replacement.get("reference", original.reference),
                strategy_id=replacement.get("strategy_id", original.strategy_id),
                time_in_force=replacement.get("time_in_force", original.time_in_force),
            )
            return new
        except Exception:
            logger.exception("interrupt: malformed replacement order — skipping")
            return None

    def _maybe_interrupt(
        self,
        requests: list[OrderRequest],
        *,
        timestamp: datetime,
        context: dict[str, Any],
    ) -> list[OrderRequest]:
        """Apply interrupt rules + handler to a batch of order requests."""
        if not self.interrupt_rules or not requests:
            return requests
        order_dicts = [self._request_to_dict(r) for r in requests]
        match = find_first_matching_rule(order_dicts, self.interrupt_rules)
        if match is None:
            return requests
        rule_name, _matched = match
        ir = InterruptRequest(
            backtest_id=context.get("backtest_id"),
            task_id=context.get("task_id"),
            timestamp=timestamp,
            rule=rule_name,
            bar_context={
                "equity": context.get("equity"),
                "cash": context.get("cash"),
                "drawdown": context.get("drawdown"),
                "prices": context.get("prices"),
            },
            pending_orders=order_dicts,
        )
        try:
            resolution = self.interrupt_handler(ir)
        except Exception:
            logger.exception("interrupt handler raised — continuing")
            return requests
        if not isinstance(resolution, InterruptResolution):
            logger.warning(
                "interrupt handler returned non-InterruptResolution: %r — continuing",
                resolution,
            )
            return requests
        if resolution.action == "skip":
            logger.info("interrupt: skipped %d orders (rule=%s)", len(requests), rule_name)
            return []
        if resolution.action == "replace":
            new_requests: list[OrderRequest] = []
            for replacement in resolution.replacement_orders or []:
                # If the replacement carries an index, prefer it; otherwise
                # match by reference and fall back to first request.
                idx = replacement.get("index")
                if isinstance(idx, int) and 0 <= idx < len(requests):
                    base = requests[idx]
                else:
                    base = requests[0]
                rebuilt = self._replacement_to_request(base, replacement)
                if rebuilt is not None:
                    new_requests.append(rebuilt)
            logger.info(
                "interrupt: replaced %d orders with %d (rule=%s)",
                len(requests),
                len(new_requests),
                rule_name,
            )
            return new_requests
        return requests

    def _submit_order(
        self,
        broker: SimulatedBrokerage,
        request: OrderRequest,
        tickets: dict[str, OrderTicket],
    ) -> None:
        order = broker.submit_order(request)
        tickets[order.order_id] = OrderTicket(
            order=order,
            events=[
                OrderEvent(
                    order_id=order.order_id,
                    timestamp=order.created_at,
                    status=order.status,
                    direction=order.side,
                    message="submitted",
                    symbol=order.symbol,
                )
            ],
        )

    def run(self, strategy: IStrategy, bars: pd.DataFrame) -> BacktestResult:
        if bars.empty:
            raise ValueError("No bars provided to backtester.")

        frame = bars.copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        if self.start is not None:
            frame = frame[frame["timestamp"] >= self.start]
        if self.end is not None:
            frame = frame[frame["timestamp"] <= self.end]
        frame = frame.sort_values(["timestamp", "vt_symbol"]).reset_index(drop=True)
        if frame.empty:
            raise ValueError("No bars remain after date filter.")

        broker = SimulatedBrokerage(
            initial_cash=self.initial_cash,
            commission_pct=self.commission_pct,
            slippage_bps=self.slippage_bps,
        )

        timestamps = frame["timestamp"].unique()
        equity_records: list[tuple[pd.Timestamp, float]] = []
        last_close_prices: dict[str, float] = {}
        tickets: dict[str, OrderTicket] = {}

        use_slice_api = hasattr(strategy, "on_data") and callable(
            getattr(strategy, "on_data", None)
        )

        history_mask = pd.Series(False, index=frame.index)

        for ts in timestamps:
            day_mask = frame["timestamp"] == ts
            history_mask |= day_mask
            day_bars = frame[day_mask]

            open_prices = {row.vt_symbol: float(row.open) for row in day_bars.itertuples()}

            fills: list[TradeData] = broker.fill_open_orders(open_prices, ts)
            if fills:
                logger.debug("[%s] %d fills", ts, len(fills))
                _apply_fills_to_tickets(tickets, fills, ts)

            history_view = frame[history_mask]
            context = {
                "history": history_view,
                "equity": broker.equity,
                "cash": broker.cash,
                "positions": dict(broker.positions),
                "prices": {
                    row.vt_symbol: float(row.close) for row in day_bars.itertuples()
                },
                "drawdown": _current_drawdown(equity_records),
            }

            if use_slice_api:
                # Single Slice for the whole timestamp — Lean-style dispatch.
                bars_by_symbol = {
                    row.vt_symbol: BarData(
                        symbol=Symbol.parse(row.vt_symbol),
                        timestamp=row.timestamp.to_pydatetime(),
                        open=float(row.open),
                        high=float(row.high),
                        low=float(row.low),
                        close=float(row.close),
                        volume=float(row.volume),
                        interval=Interval.DAY,
                    )
                    for row in day_bars.itertuples()
                }
                slice_ = Slice(
                    timestamp=pd.Timestamp(ts).to_pydatetime(),
                    bars=bars_by_symbol,
                )
                requests = list(strategy.on_data(slice_, context))
                requests = self._maybe_interrupt(
                    requests,
                    timestamp=pd.Timestamp(ts).to_pydatetime(),
                    context=context,
                )
                for request in requests:
                    self._submit_order(broker, request, tickets)
                for row in day_bars.itertuples():
                    last_close_prices[row.vt_symbol] = float(row.close)
            else:
                for row in day_bars.itertuples():
                    bar = BarData(
                        symbol=Symbol.parse(row.vt_symbol),
                        timestamp=row.timestamp.to_pydatetime(),
                        open=float(row.open),
                        high=float(row.high),
                        low=float(row.low),
                        close=float(row.close),
                        volume=float(row.volume),
                        interval=Interval.DAY,
                    )
                    requests = list(strategy.on_bar(bar, context))
                    requests = self._maybe_interrupt(
                        requests,
                        timestamp=bar.timestamp,
                        context=context,
                    )
                    for request in requests:
                        self._submit_order(broker, request, tickets)
                    last_close_prices[row.vt_symbol] = float(row.close)

            broker.mark_to_market(last_close_prices)
            equity_records.append((ts, broker.equity))

        equity = pd.Series(
            [eq for _, eq in equity_records],
            index=pd.to_datetime([t for t, _ in equity_records]),
            name="equity",
        )
        trades = pd.DataFrame(
            [
                {
                    "timestamp": t.timestamp,
                    "vt_symbol": t.symbol.vt_symbol,
                    "side": t.side.value,
                    "quantity": t.quantity,
                    "price": t.price,
                    "commission": t.commission,
                    "slippage": t.slippage,
                    "strategy_id": t.strategy_id,
                }
                for t in broker.trades
            ]
        )
        orders = pd.DataFrame(
            [
                {
                    "order_id": o.order_id,
                    "vt_symbol": o.symbol.vt_symbol,
                    "side": o.side.value,
                    "quantity": o.quantity,
                    "price": o.price,
                    "status": o.status.value,
                    "created_at": o.created_at,
                }
                for o in broker.orders.values()
            ]
        )

        summary = summarise(equity, trades)

        return BacktestResult(
            equity_curve=equity,
            trades=trades,
            orders=orders,
            tickets=list(tickets.values()),
            summary=summary,
            start=pd.Timestamp(timestamps[0]).to_pydatetime() if len(timestamps) else None,
            end=pd.Timestamp(timestamps[-1]).to_pydatetime() if len(timestamps) else None,
            initial_cash=self.initial_cash,
            final_equity=broker.equity,
        )


def _current_drawdown(records: list[tuple[pd.Timestamp, float]]) -> float:
    if not records:
        return 0.0
    series = pd.Series([eq for _, eq in records])
    cummax = series.cummax()
    dd = (series - cummax) / cummax
    return float(dd.iloc[-1])


def _apply_fills_to_tickets(
    tickets: dict[str, OrderTicket],
    fills: list[TradeData],
    ts: pd.Timestamp,
) -> None:
    """Record each fill on the corresponding ticket's event stream."""
    for trade in fills:
        ticket = tickets.get(trade.order_id)
        if ticket is None:
            continue
        ticket.append_event(
            OrderEvent(
                order_id=trade.order_id,
                timestamp=pd.Timestamp(ts).to_pydatetime(),
                status=ticket.order.status,
                direction=trade.side,
                fill_price=trade.price,
                fill_quantity=trade.quantity,
                fee=trade.commission,
                message="filled",
                symbol=trade.symbol,
            )
        )
