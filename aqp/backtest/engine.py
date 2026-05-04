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
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.backtest.base import BaseBacktestEngine
from aqp.backtest.broker_sim import SimulatedBrokerage
from aqp.backtest.capabilities import EngineCapabilities
from aqp.backtest.interrupts import (
    InterruptHandler,
    InterruptRequest,
    InterruptResolution,
    NullInterruptHandler,
    find_first_matching_rule,
)
from aqp.backtest.metrics import summarise
from aqp.core.interfaces import (
    IAlphaModel,
    IExecutionModel,
    IPortfolioConstructionModel,
    IRiskManagementModel,
    IStrategy,
)
from aqp.core.registry import register
from aqp.core.slice import Slice
from aqp.core.types import (
    BarData,
    EventType,
    FillEvent_Msg,
    Interval,
    MarketEvent,
    OrderEvent,
    OrderEvent_Msg,
    OrderRequest,
    OrderTicket,
    SignalEvent,
    Symbol,
    TradeData,
)
from aqp.observability import get_tracer

logger = logging.getLogger(__name__)
_tracer = get_tracer("aqp.backtest.engine")


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
    # Phase 1: append-only stream of every Event consumed by the engine bus.
    # Carries enough context (MarketEvent.data, SignalEvent.signals,
    # OrderEvent_Msg.request, FillEvent_Msg.trade) to fully reconstruct the
    # run via :func:`aqp.backtest.replay.replay_event_log`.
    event_log: list[Any] = field(default_factory=list)


@register("EventDrivenBacktester")
class EventDrivenBacktester(BaseBacktestEngine):
    """Chronologically replays bars and executes orders at next bar's open."""

    capabilities = EngineCapabilities(
        name="event-driven",
        description=(
            "Lean-style chronological bar replay with simulated brokerage; "
            "the per-bar Python path used for true async agent dispatch via "
            "the strategy `context['agents']` dispatcher."
        ),
        supports_signals=True,
        supports_orders=True,
        supports_callbacks=True,
        supports_multi_asset=True,
        supports_short_selling=True,
        supports_leverage=False,
        supports_stops=False,
        supports_limit_orders=True,
        supports_event_driven=True,
        supports_per_bar_python=True,
        supports_interrupts=True,
        supports_walk_forward=True,
        supports_monte_carlo=True,
        license="MIT",
        notes="Default engine. Use this when you need agents/ML running per-bar in pure Python.",
    )

    def __init__(
        self,
        initial_cash: float = 100000.0,
        commission_pct: float = 0.0005,
        slippage_bps: float = 2.0,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        interrupt_rules: list[dict[str, Any]] | None = None,
        interrupt_handler: InterruptHandler | None = None,
        agent_dispatcher: Any | None = None,
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
        # The dispatcher exposed via ``context['agents']`` so a strategy can
        # consult an agent inside on_bar/on_data. Lazily initialised so the
        # AgentRuntime import is only paid for runs that actually use it.
        self._agent_dispatcher = agent_dispatcher

    def _get_agent_dispatcher(self) -> Any:
        """Return the agent dispatcher exposed through ``context['agents']``.

        Lazily resolves the default :class:`AgentDispatcher` so backtests
        that never use the consult primitive don't pay the import cost.
        """
        if self._agent_dispatcher is not None:
            return self._agent_dispatcher
        try:
            from aqp.strategies.agentic.agent_dispatcher import get_default_dispatcher

            self._agent_dispatcher = get_default_dispatcher()
        except Exception:
            self._agent_dispatcher = _NoopDispatcher()
        return self._agent_dispatcher

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
    ) -> Any:
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
        return order

    def run(self, strategy: IStrategy, bars: pd.DataFrame) -> BacktestResult:
        # Trace the backtest at the entry point so the entire run shows up as a
        # single span in Jaeger; downstream broker/strategy spans become children
        # via the active context.  Attributes are kept low-cardinality.
        with _tracer.start_as_current_span("backtest.run") as span:
            try:
                span.set_attribute("backtest.engine", "EventDrivenBacktester")
                span.set_attribute("backtest.strategy", type(strategy).__name__)
                span.set_attribute("backtest.bars_count", int(len(bars)))
                span.set_attribute("backtest.initial_cash", float(self.initial_cash))
            except Exception:  # noqa: BLE001 - tracing must never affect logic
                pass
            return self._run_impl(strategy, bars, span=span)

    def _run_impl(
        self,
        strategy: IStrategy,
        bars: pd.DataFrame,
        *,
        span: Any | None = None,
    ) -> BacktestResult:
        """Drain a ``deque[Event]`` per the Lean-style five-stage flow.

        Per timestamp ``ts`` the engine seeds ``MarketEvent``s for every bar
        in ``ts``, then drains the queue: each ``MarketEvent`` is fanned out
        to the strategy which may emit ``Signal`` rows; those are wrapped
        into a single ``SignalEvent`` per-timestamp and converted into one
        ``OrderEvent_Msg`` per ``OrderRequest``. The simulated broker fills
        at the next ``ts``'s open prices and surfaces ``FillEvent_Msg``s
        which are also drained from the same queue. Every event consumed is
        appended to ``event_log`` so :func:`aqp.backtest.replay.replay_event_log`
        can reconstruct the run deterministically.
        """
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
        peak_prices: dict[str, float] = {}
        tickets: dict[str, OrderTicket] = {}
        event_log: list[Any] = []
        signal_records: list[dict[str, Any]] = []

        use_slice_api = hasattr(strategy, "on_data") and callable(
            getattr(strategy, "on_data", None)
        )

        history_mask = pd.Series(False, index=frame.index)

        # Outer chronological loop drives the queue; each iteration processes
        # one timestamp's MarketEvents (and the SignalEvent/OrderEvent_Msg/
        # FillEvent_Msg cascades they trigger) before advancing time.
        for ts in timestamps:
            day_mask = frame["timestamp"] == ts
            history_mask |= day_mask
            day_bars = frame[day_mask]

            open_prices = {
                row.vt_symbol: float(row.open) for row in day_bars.itertuples()
            }

            queue: deque[Any] = deque()

            # Stage 0: drain pending fills using THIS bar's open prices.
            fills: list[TradeData] = broker.fill_open_orders(open_prices, ts)
            for trade in fills:
                queue.append(FillEvent_Msg(trade=trade))

            # Stage 1: seed one MarketEvent per (ts, symbol). Order is stable
            # so deterministic replay reproduces the same handler sequence.
            ts_pydt = pd.Timestamp(ts).to_pydatetime()
            bars_by_symbol: dict[str, BarData] = {}
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
                bars_by_symbol[row.vt_symbol] = bar
                queue.append(MarketEvent(data=bar))

            history_view = frame[history_mask]
            close_prices = {
                vt: float(b.close) for vt, b in bars_by_symbol.items()
            }
            for vt, close in close_prices.items():
                prev_peak = peak_prices.get(vt, close)
                peak_prices[vt] = max(prev_peak, close)
            context = {
                "history": history_view,
                "equity": broker.equity,
                "cash": broker.cash,
                "positions": dict(broker.positions),
                "prices": close_prices,
                "peak_prices": dict(peak_prices),
                "drawdown": _current_drawdown(equity_records),
                "current_time": ts_pydt,
                "agents": self._get_agent_dispatcher(),
            }

            # The strategy is dispatched once per timestamp — the queue is
            # the canonical event bus, MarketEvents are just the seed.  This
            # mirrors Lean's OnFrameworkData ordering: drain MarketEvents
            # into a single Slice, then run alpha/portfolio/risk/execution.
            seen_market_events: list[MarketEvent] = []
            deferred: deque[Any] = deque()
            while queue:
                event = queue.popleft()
                if event.type == EventType.MARKET:
                    event_log.append(event)
                    seen_market_events.append(event)
                elif event.type == EventType.FILL:
                    event_log.append(event)
                    _apply_fills_to_tickets(tickets, [event.trade], ts)
                else:
                    # Defer Signal / Order events until after the strategy
                    # has had a chance to emit its own.
                    deferred.append(event)

            requests: list[OrderRequest] = []
            if use_slice_api and seen_market_events:
                slice_ = Slice(
                    timestamp=ts_pydt,
                    bars={
                        ev.data.symbol.vt_symbol: ev.data
                        for ev in seen_market_events
                    },
                )
                requests = list(strategy.on_data(slice_, context))
            elif seen_market_events:
                for ev in seen_market_events:
                    requests.extend(strategy.on_bar(ev.data, context))

            requests = self._maybe_interrupt(
                requests,
                timestamp=ts_pydt,
                context=context,
            )

            queue = deferred

            captured_signals: list[Any] = getattr(strategy, "_last_signals", None) or []
            if captured_signals:
                queue.append(
                    SignalEvent(signals=list(captured_signals), timestamp=ts_pydt)
                )
                strategy._last_signals = []  # type: ignore[attr-defined]

            for request in requests:
                queue.append(OrderEvent_Msg(request=request, timestamp=ts_pydt))

            # Drain the cascade.  OrderEvent_Msg → broker.submit_order;
            # SignalEvent → metadata only (signals already drove requests).
            # Logging happens after dispatch so the OrderEvent_Msg captures
            # the broker-assigned ``order_id`` (required by the replay path).
            while queue:
                event = queue.popleft()
                if event.type == EventType.SIGNAL:
                    event_log.append(event)
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
                    order = self._submit_order(broker, event.request, tickets)
                    event.order_id = order.order_id
                    event_log.append(event)
                elif event.type == EventType.FILL:
                    event_log.append(event)
                    _apply_fills_to_tickets(tickets, [event.trade], ts)

            # End-of-bar accounting (not on the bus — pure broker bookkeeping).
            for vt, close in close_prices.items():
                last_close_prices[vt] = close
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
        signals_df = (
            pd.DataFrame(signal_records)
            if signal_records
            else pd.DataFrame()
        )

        return BacktestResult(
            equity_curve=equity,
            trades=trades,
            orders=orders,
            signals=signals_df,
            tickets=list(tickets.values()),
            summary=summary,
            start=pd.Timestamp(timestamps[0]).to_pydatetime() if len(timestamps) else None,
            end=pd.Timestamp(timestamps[-1]).to_pydatetime() if len(timestamps) else None,
            initial_cash=self.initial_cash,
            final_equity=broker.equity,
            event_log=event_log,
        )


def _current_drawdown(records: list[tuple[pd.Timestamp, float]]) -> float:
    if not records:
        return 0.0
    series = pd.Series([eq for _, eq in records])
    cummax = series.cummax()
    dd = (series - cummax) / cummax
    return float(dd.iloc[-1])


class _NoopDispatcher:
    """Fallback dispatcher when the agent runtime is unavailable.

    Strategies still see a ``context['agents']`` object so they don't have
    to branch on availability — calls just return ``None``.
    """

    def consult(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def consult_async(self, *args: Any, **kwargs: Any) -> Any:
        return None


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
