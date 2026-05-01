"""The async paper/live trading runtime.

This engine is the live-mode twin of :class:`aqp.backtest.engine.EventDrivenBacktester`.
It consumes an :class:`aqp.core.interfaces.IMarketDataFeed`, routes orders
to an :class:`aqp.core.interfaces.IBrokerage` (sync or async), writes every
signal/order/fill to the shared execution ledger, and publishes progress to
Redis so the existing ``/chat/stream/<task_id>`` WebSocket works unchanged.

The design goal is **backtest ≡ paper ≡ live** parity so the same
``IStrategy`` object (e.g. ``FrameworkAlgorithm``) runs in any of the three
modes without modification.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.core.interfaces import (
    IAsyncBrokerage,
    IBrokerage,
    IMarketDataFeed,
    IStrategy,
    ITimeProvider,
)
from aqp.core.types import BarData, OrderData, OrderRequest, TradeData
from aqp.observability import traced
from aqp.persistence.db import get_session
from aqp.persistence.models import (
    Fill,
    LedgerEntry,
    OrderRecord,
    PaperTradingRun,
)
from aqp.risk.kill_switch import is_engaged
from aqp.risk.manager import RiskManager
from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.trading.clock import RealTimeClock
from aqp.trading.state import PaperSessionState

logger = logging.getLogger(__name__)


@dataclass
class PaperSessionConfig:
    """Runtime knobs for a paper session (plain dataclass, JSON serialisable)."""

    run_name: str = "paper-adhoc"
    heartbeat_seconds: int = 30
    state_flush_every_bars: int = 10
    history_window_bars: int = 500
    max_bars: int | None = None
    initial_cash: float = 100000.0
    stop_on_kill_switch: bool = True
    dry_run: bool = False  # True → use SimulatedBrokerage regardless of cfg

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_name": self.run_name,
            "heartbeat_seconds": self.heartbeat_seconds,
            "state_flush_every_bars": self.state_flush_every_bars,
            "history_window_bars": self.history_window_bars,
            "max_bars": self.max_bars,
            "initial_cash": self.initial_cash,
            "stop_on_kill_switch": self.stop_on_kill_switch,
            "dry_run": self.dry_run,
        }


@dataclass
class PaperSessionResult:
    run_id: str
    task_id: str | None
    status: str
    bars_seen: int
    orders_submitted: int
    fills: int
    final_equity: float
    realized_pnl: float
    error: str | None = None
    config: dict[str, Any] = field(default_factory=dict)


class PaperTradingSession:
    """Async orchestration of a single paper/live trading run."""

    def __init__(
        self,
        strategy: IStrategy,
        brokerage: IBrokerage,
        feed: IMarketDataFeed,
        risk: RiskManager | None = None,
        clock: ITimeProvider | None = None,
        config: PaperSessionConfig | None = None,
        task_id: str | None = None,
    ) -> None:
        self.strategy = strategy
        self.brokerage = brokerage
        self.feed = feed
        self.risk = risk or RiskManager()
        self.clock = clock or RealTimeClock()
        self.config = config or PaperSessionConfig()
        self.task_id = task_id

        self.run_id = f"paper-{uuid.uuid4().hex[:10]}"
        self._shutdown = asyncio.Event()
        self._bars_seen = 0
        self._orders_submitted = 0
        self._fills = 0
        self._error: str | None = None
        self._history: list[dict[str, Any]] = []
        self._known_order_ids: set[str] = set()
        self._started_at = self.clock.now()
        # Peak/last close per symbol — fed to risk models that need
        # ``context["peak_prices"]`` (e.g. TrailingStopRiskManagementModel).
        self._last_prices: dict[str, float] = {}
        self._peak_prices: dict[str, float] = {}
        # Runner can set this before calling ``run()`` so ``_connect`` can
        # subscribe the feed for the entire desired universe in one call.
        self.pending_universe: list[Any] = []

    # ---------------------------------------------------------------- API

    def request_shutdown(self, reason: str = "manual") -> None:
        """Signal the main loop to drain and exit gracefully."""
        logger.info("shutdown requested for %s: %s", self.run_id, reason)
        self._shutdown.set()

    @traced("paper.session.run")
    async def run(self) -> PaperSessionResult:
        """Main event loop — returns when the feed ends or shutdown is signalled."""
        status = "running"
        self._persist_run_row(status=status)
        self._progress("starting", f"Starting paper session {self.run_id}")

        try:
            await self._connect()
            async for bar in self._iter_feed():
                if self._shutdown.is_set():
                    self._progress("stopping", "Shutdown signalled")
                    break
                if self.config.stop_on_kill_switch and is_engaged():
                    self._progress("stopping", "Kill switch engaged; draining")
                    self._shutdown.set()
                    break
                await self._on_bar(bar)
                self._bars_seen += 1
                if (
                    self.config.state_flush_every_bars
                    and self._bars_seen % self.config.state_flush_every_bars == 0
                ):
                    self._flush_state()
                if self.config.max_bars and self._bars_seen >= self.config.max_bars:
                    self._progress("stopping", "max_bars reached")
                    break
            status = "completed"
        except asyncio.CancelledError:  # pragma: no cover — cooperative shutdown
            status = "cancelled"
            raise
        except Exception as exc:  # noqa: BLE001
            status = "error"
            self._error = str(exc)
            logger.exception("paper session %s failed", self.run_id)
            if self.task_id:
                emit_error(self.task_id, str(exc))
        finally:
            await self._disconnect()
            self._finalise(status)

        account_equity = self._current_equity()
        result = PaperSessionResult(
            run_id=self.run_id,
            task_id=self.task_id,
            status=status,
            bars_seen=self._bars_seen,
            orders_submitted=self._orders_submitted,
            fills=self._fills,
            final_equity=account_equity,
            realized_pnl=self._realized_pnl(),
            error=self._error,
            config=self.config.as_dict(),
        )
        if status == "completed" and self.task_id:
            emit_done(self.task_id, result.__dict__)
        return result

    # ----------------------------------------------------- internals

    async def _connect(self) -> None:
        if isinstance(self.brokerage, IAsyncBrokerage):
            await self.brokerage.connect_async()
        else:
            await _maybe_run_in_thread(self.brokerage.connect)
        await self.feed.connect()
        if self.pending_universe:
            await self.feed.subscribe(self.pending_universe)
            logger.info(
                "subscribed feed '%s' to %d symbols",
                self.feed.name,
                len(self.pending_universe),
            )

    async def _disconnect(self) -> None:
        try:
            await self.feed.disconnect()
        except Exception:
            logger.exception("feed disconnect failed")
        try:
            if isinstance(self.brokerage, IAsyncBrokerage):
                await self.brokerage.disconnect_async()
            else:
                await _maybe_run_in_thread(self.brokerage.disconnect)
        except Exception:
            logger.exception("brokerage disconnect failed")

    async def _iter_feed(self) -> Any:
        """Wrap ``feed.stream()`` so timeouts hit the heartbeat check."""
        stream = self.feed.stream()
        while True:
            if self._shutdown.is_set():
                break
            try:
                bar = await asyncio.wait_for(stream.__anext__(), timeout=self.config.heartbeat_seconds)
            except TimeoutError:
                self._progress("heartbeat", "no bars this interval")
                continue
            except StopAsyncIteration:
                break
            yield bar

    @traced("paper.session.bar")
    async def _on_bar(self, bar: BarData) -> None:
        self._append_history(bar)
        # Track per-symbol peaks so trailing-stop / drawdown-per-security
        # risk models work in live paper sessions the same way they do in
        # the event-driven backtester.
        close = float(bar.close)
        vt = bar.symbol.vt_symbol
        self._last_prices[vt] = close
        prev_peak = self._peak_prices.get(vt, close)
        self._peak_prices[vt] = max(prev_peak, close)
        context = {
            "history": self._history_frame(),
            "current_time": bar.timestamp,
            "account": self._account_snapshot(),
            "positions": self._positions_snapshot(),
            "prices": dict(self._last_prices),
            "peak_prices": dict(self._peak_prices),
            "strategy_id": getattr(self.strategy, "strategy_id", None),
        }
        try:
            order_requests = list(self.strategy.on_bar(bar, context))
        except Exception:
            logger.exception("strategy.on_bar error")
            self._ledger("STRATEGY", "error", "strategy.on_bar raised", level="error", vt_symbol=bar.vt_symbol)
            return

        for request in order_requests:
            await self._submit_order(request)

        await self._drain_order_updates()

    @traced("paper.session.submit_order")
    async def _submit_order(self, request: OrderRequest) -> OrderData | None:
        equity = self._current_equity()
        price = request.price or self._last_price(request.symbol.vt_symbol) or 0.0
        notional = abs(request.quantity) * price
        breaches = self.risk.check_pretrade(
            equity=equity,
            positions=self._positions_map(),
            order_notional=notional,
            order_symbol=request.symbol.vt_symbol,
        )
        if any(b.severity in {"block", "critical"} for b in breaches):
            self._ledger(
                "RISK",
                f"Pre-trade block on {request.symbol.vt_symbol}",
                level="warn",
                vt_symbol=request.symbol.vt_symbol,
                payload={"breaches": [b.__dict__ for b in breaches]},
            )
            return None

        try:
            if isinstance(self.brokerage, IAsyncBrokerage):
                order = await self.brokerage.submit_order_async(request)
            else:
                order = await _maybe_run_in_thread(self.brokerage.submit_order, request)
        except Exception as exc:  # noqa: BLE001
            logger.exception("brokerage.submit_order failed")
            self._ledger(
                "ORDER",
                f"submit failed: {exc}",
                level="error",
                vt_symbol=request.symbol.vt_symbol,
            )
            return None

        self._orders_submitted += 1
        self._known_order_ids.add(order.order_id)
        self._persist_order(order)
        self._ledger(
            "ORDER",
            f"{order.side.value} {order.quantity} {order.symbol.vt_symbol} @ {order.price}",
            vt_symbol=order.symbol.vt_symbol,
            payload={"order_id": order.order_id, "status": order.status.value},
        )
        return order

    async def _drain_order_updates(self) -> None:
        """Poll the simulated brokerage's open-order state machine one step.

        Real async brokerages push updates via ``stream_order_updates`` in a
        background task spawned by the concrete adapter; this keeps the
        simulated path alive for dry-runs without creating a second event loop.
        """
        fill_method = getattr(self.brokerage, "fill_open_orders", None)
        if fill_method is None:
            return
        prices = self._price_map()
        trades: list[TradeData] = fill_method(prices, self.clock.now())
        if trades:
            if hasattr(self.brokerage, "mark_to_market"):
                self.brokerage.mark_to_market(prices)
            for trade in trades:
                self._fills += 1
                self._persist_fill(trade)
                self._ledger(
                    "FILL",
                    f"{trade.side.value} {trade.quantity} {trade.symbol.vt_symbol} @ {trade.price}",
                    vt_symbol=trade.symbol.vt_symbol,
                    payload={
                        "trade_id": trade.trade_id,
                        "order_id": trade.order_id,
                        "commission": trade.commission,
                        "slippage": trade.slippage,
                    },
                )

    # ----------------------------------------------------- helpers

    def _append_history(self, bar: BarData) -> None:
        self._history.append(
            {
                "timestamp": bar.timestamp,
                "vt_symbol": bar.vt_symbol,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
        )
        window = self.config.history_window_bars
        if window and len(self._history) > window * 10:
            self._history = self._history[-window * 5 :]

    def _history_frame(self) -> pd.DataFrame:
        if not self._history:
            return pd.DataFrame(
                columns=["timestamp", "vt_symbol", "open", "high", "low", "close", "volume"]
            )
        return pd.DataFrame(self._history)

    def _account_snapshot(self) -> dict[str, Any]:
        try:
            account = self.brokerage.query_account()
            return {"cash": account.cash, "equity": account.equity}
        except Exception:
            return {"cash": 0.0, "equity": self._current_equity()}

    def _positions_snapshot(self) -> list[dict[str, Any]]:
        try:
            return [
                {
                    "vt_symbol": p.symbol.vt_symbol,
                    "quantity": p.quantity,
                    "average_price": p.average_price,
                    "direction": p.direction.value,
                }
                for p in self.brokerage.query_positions()
            ]
        except Exception:
            return []

    def _positions_map(self) -> dict[str, Any]:
        try:
            return {p.symbol.vt_symbol: p for p in self.brokerage.query_positions()}
        except Exception:
            return {}

    def _current_equity(self) -> float:
        try:
            return float(self.brokerage.query_account().equity)
        except Exception:
            return float(self.config.initial_cash)

    def _realized_pnl(self) -> float:
        total = 0.0
        try:
            for pos in self.brokerage.query_positions():
                total += float(pos.realized_pnl or 0.0)
        except Exception:
            pass
        return total

    def _last_price(self, vt_symbol: str) -> float | None:
        for row in reversed(self._history):
            if row["vt_symbol"] == vt_symbol:
                return float(row["close"])
        return None

    def _price_map(self) -> dict[str, float]:
        seen: dict[str, float] = {}
        for row in reversed(self._history):
            if row["vt_symbol"] in seen:
                continue
            seen[row["vt_symbol"]] = float(row["close"])
        return seen

    # ---------------------------------------------------- persistence

    def _persist_run_row(self, status: str) -> None:
        try:
            with get_session() as s:
                s.add(
                    PaperTradingRun(
                        id=self.run_id,
                        task_id=self.task_id,
                        run_name=self.config.run_name,
                        strategy_id=getattr(self.strategy, "strategy_id", None),
                        brokerage=self.brokerage.name,
                        feed=self.feed.name,
                        status=status,
                        started_at=self._started_at,
                        initial_cash=self.config.initial_cash,
                        config=self.config.as_dict(),
                    )
                )
        except Exception:
            logger.exception("could not persist PaperTradingRun row (DB down?)")

    def _persist_order(self, order: OrderData) -> None:
        try:
            with get_session() as s:
                s.add(
                    OrderRecord(
                        id=order.order_id,
                        strategy_id=getattr(self.strategy, "strategy_id", None),
                        vt_symbol=order.symbol.vt_symbol,
                        side=order.side.value,
                        order_type=order.order_type.value,
                        quantity=float(order.quantity),
                        price=float(order.price) if order.price else None,
                        status=order.status.value,
                        reference=f"paper:{self.run_id}",
                    )
                )
        except Exception:
            logger.exception("could not persist OrderRecord")

    def _persist_fill(self, trade: TradeData) -> None:
        try:
            with get_session() as s:
                s.add(
                    Fill(
                        order_id=trade.order_id,
                        vt_symbol=trade.symbol.vt_symbol,
                        side=trade.side.value,
                        quantity=float(trade.quantity),
                        price=float(trade.price),
                        commission=float(trade.commission or 0.0),
                        slippage=float(trade.slippage or 0.0),
                    )
                )
        except Exception:
            logger.exception("could not persist Fill")

    def _ledger(
        self,
        entry_type: str,
        message: str,
        *,
        level: str = "info",
        vt_symbol: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        payload = dict(payload or {})
        payload.setdefault("run_id", self.run_id)
        payload.setdefault("vt_symbol", vt_symbol)
        try:
            with get_session() as s:
                s.add(
                    LedgerEntry(
                        strategy_id=getattr(self.strategy, "strategy_id", None),
                        entry_type=entry_type,
                        level=level,
                        message=message,
                        payload=payload,
                    )
                )
        except Exception:
            logger.exception("ledger write failed")

    def _flush_state(self) -> None:
        state = PaperSessionState(
            run_id=self.run_id,
            task_id=self.task_id,
            run_name=self.config.run_name,
            strategy_id=getattr(self.strategy, "strategy_id", "unknown"),
            brokerage=self.brokerage.name,
            feed=self.feed.name,
            started_at=self._started_at,
            last_heartbeat_at=self.clock.now(),
            bars_seen=self._bars_seen,
            orders_submitted=self._orders_submitted,
            fills=self._fills,
            cash=self._account_snapshot().get("cash", 0.0),
            equity=self._current_equity(),
            realized_pnl=self._realized_pnl(),
        )
        try:
            with get_session() as s:
                row = s.get(PaperTradingRun, self.run_id)
                if row is not None:
                    row.state = state.to_dict()
                    row.bars_seen = self._bars_seen
                    row.orders_submitted = self._orders_submitted
                    row.fills = self._fills
                    row.final_equity = state.equity
                    row.last_heartbeat_at = state.last_heartbeat_at
        except Exception:
            logger.exception("state flush failed")

    def _finalise(self, status: str) -> None:
        try:
            with get_session() as s:
                row = s.get(PaperTradingRun, self.run_id)
                if row is not None:
                    row.status = status
                    row.stopped_at = datetime.utcnow()
                    row.final_equity = self._current_equity()
                    row.realized_pnl = self._realized_pnl()
                    row.bars_seen = self._bars_seen
                    row.orders_submitted = self._orders_submitted
                    row.fills = self._fills
                    row.error = self._error
        except Exception:
            logger.exception("finalise row update failed")

    # ----------------------------------------------------- progress

    def _progress(self, stage: str, message: str) -> None:
        logger.info("[%s] %s: %s", self.run_id, stage, message)
        if self.task_id:
            emit(
                self.task_id,
                stage,
                message,
                run_id=self.run_id,
                bars_seen=self._bars_seen,
                orders=self._orders_submitted,
                fills=self._fills,
                equity=self._current_equity(),
                ts=time.time(),
            )


async def _maybe_run_in_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a sync callable in a worker thread so it doesn't block the loop."""
    return await asyncio.to_thread(func, *args, **kwargs)
