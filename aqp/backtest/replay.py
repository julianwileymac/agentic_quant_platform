"""Deterministic event-log replay for ``BacktestResult``.

The Phase 1 refactor of :class:`aqp.backtest.engine.EventDrivenBacktester`
records every ``Event`` consumed by the engine bus into
``BacktestResult.event_log``. This module reconstructs the equity curve,
trades, and order tickets by walking that stream alone — without
re-reading the source bars — which catches any non-determinism leaking
into a strategy via wall-clock timestamps, ``random``, or hidden state.

Lean's determinism contract is "same data + same code = same run". Ours
is stricter: "same event log = same result", regardless of the strategy
implementation. If a refactor of the strategy changes the equity curve
without changing the events it emits/consumes, the diff is in the broker
bookkeeping path, which is where it belongs.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.backtest.broker_sim import SimulatedBrokerage
from aqp.backtest.engine import BacktestResult, _apply_fills_to_tickets
from aqp.backtest.metrics import summarise
from aqp.core.types import (
    EventType,
    OrderEvent,
    OrderTicket,
    TradeData,
)

logger = logging.getLogger(__name__)


def replay_event_log(
    event_log: list[Any],
    *,
    initial_cash: float,
    commission_pct: float = 0.0005,
    slippage_bps: float = 2.0,
) -> BacktestResult:
    """Reconstruct a :class:`BacktestResult` from a captured event log.

    Parameters
    ----------
    event_log
        The ``BacktestResult.event_log`` list produced by an earlier run.
    initial_cash, commission_pct, slippage_bps
        Must match the engine that produced ``event_log``; otherwise the
        broker accounting will diverge.

    Returns
    -------
    BacktestResult
        Equivalent to the original — equity curve, trades, orders, signals,
        tickets, and event_log are byte-for-byte identical when the original
        run was deterministic.
    """
    if not event_log:
        raise ValueError("Cannot replay an empty event log.")

    broker = SimulatedBrokerage(
        initial_cash=float(initial_cash),
        commission_pct=float(commission_pct),
        slippage_bps=float(slippage_bps),
    )
    tickets: dict[str, OrderTicket] = {}
    equity_records: list[tuple[pd.Timestamp, float]] = []
    last_close_prices: dict[str, float] = {}
    signal_records: list[dict[str, Any]] = []
    replayed: list[Any] = []
    current_ts: datetime | None = None

    def _flush_equity(ts: datetime) -> None:
        if last_close_prices:
            broker.mark_to_market(last_close_prices)
        equity_records.append((pd.Timestamp(ts), broker.equity))

    for event in event_log:
        replayed.append(event)
        ev_ts = getattr(event, "timestamp", None) or current_ts
        if ev_ts is None:
            continue
        if current_ts is not None and ev_ts != current_ts and last_close_prices:
            _flush_equity(current_ts)
        current_ts = ev_ts

        if event.type == EventType.MARKET:
            bar = event.data
            last_close_prices[bar.symbol.vt_symbol] = float(bar.close)
        elif event.type == EventType.SIGNAL:
            for sig in event.signals:
                signal_records.append(
                    {
                        "timestamp": event.timestamp,
                        "vt_symbol": sig.symbol.vt_symbol,
                        "direction": sig.direction.value
                        if hasattr(sig.direction, "value")
                        else str(sig.direction),
                        "strength": float(sig.strength),
                        "confidence": float(sig.confidence),
                        "horizon_days": int(sig.horizon_days),
                        "source": sig.source,
                    }
                )
        elif event.type == EventType.ORDER:
            order = broker.submit_order(event.request)
            # Preserve the original broker-assigned id so downstream
            # ``FillEvent_Msg.trade.order_id`` correlates and the replay
            # produces an equity curve identical to the source run.
            if event.order_id and event.order_id != order.order_id:
                broker.orders.pop(order.order_id, None)
                order.order_id = event.order_id
                broker.orders[event.order_id] = order
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
        elif event.type == EventType.FILL:
            trade: TradeData = event.trade
            # Mirror the engine's fill-at-open path: re-execute the fill on
            # the broker so cash + positions reflect the same sequence.
            # Uses the broker's own ``_apply_fill`` (which mutates positions,
            # cash, order status, and appends to ``trades``) — guarantees the
            # final ``BacktestResult`` is byte-identical to the original run.
            order = broker.orders.get(trade.order_id)
            if order is not None:
                broker._apply_fill(  # type: ignore[attr-defined]
                    order, trade.price, trade.timestamp
                )
            _apply_fills_to_tickets(tickets, [trade], pd.Timestamp(trade.timestamp))

    if current_ts is not None and last_close_prices:
        _flush_equity(current_ts)

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
    signals_df = (
        pd.DataFrame(signal_records) if signal_records else pd.DataFrame()
    )
    summary = summarise(equity, trades)
    start = equity_records[0][0].to_pydatetime() if equity_records else None
    end = equity_records[-1][0].to_pydatetime() if equity_records else None
    return BacktestResult(
        equity_curve=equity,
        trades=trades,
        orders=orders,
        signals=signals_df,
        tickets=list(tickets.values()),
        summary=summary,
        start=start,
        end=end,
        initial_cash=float(initial_cash),
        final_equity=broker.equity,
        event_log=replayed,
    )


def diff_event_logs(left: list[Any], right: list[Any]) -> list[dict[str, Any]]:
    """Return a list of ``{index, side, type, repr}`` diffs between two logs.

    Convenience helper for tests asserting determinism: an empty list means
    the two runs produced identical event streams.
    """
    diffs: list[dict[str, Any]] = []
    n = min(len(left), len(right))
    for i in range(n):
        a, b = left[i], right[i]
        if type(a) is not type(b) or repr(a) != repr(b):
            diffs.append(
                {"index": i, "left": repr(a)[:200], "right": repr(b)[:200]}
            )
    if len(left) > n:
        for i, ev in enumerate(left[n:], start=n):
            diffs.append({"index": i, "side": "left_only", "value": repr(ev)[:200]})
    elif len(right) > n:
        for i, ev in enumerate(right[n:], start=n):
            diffs.append({"index": i, "side": "right_only", "value": repr(ev)[:200]})
    return diffs


__all__ = ["diff_event_logs", "replay_event_log"]
