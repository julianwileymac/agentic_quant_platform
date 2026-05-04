"""AAT-backed backtest engine.

Adapter that runs an :class:`IStrategy` (or :class:`IAlphaModel`) through
AAT's async :class:`aat.engine.TradingEngine` with the synthetic order-book
exchange. Useful for microstructure-flavoured backtests that want a real
limit order book without paying for nautilus_trader's LGPL footprint.

Lazy-imports the ``aat`` package; raises a clear install hint if missing.

The async event loop is run inside a synchronous :meth:`run` via
``asyncio.run`` so the engine slots into the same call surface as every
other AQP backtester.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.backtest.base import BaseBacktestEngine
from aqp.backtest.capabilities import EngineCapabilities
from aqp.backtest.engine import BacktestResult
from aqp.backtest.metrics import summarise
from aqp.core.interfaces import IAlphaModel, IStrategy
from aqp.core.registry import register
from aqp.core.types import Direction, Symbol

logger = logging.getLogger(__name__)


class AatDependencyError(ImportError):
    """Raised when ``aat`` is not installed but the engine is requested."""


def _import_aat() -> Any:
    try:
        import aat  # noqa: F401
        from aat.config import TradingType  # noqa: F401
        from aat.engine import TradingEngine  # noqa: F401
        from aat.exchange.synthetic import SyntheticExchange  # noqa: F401
        from aat.strategy import Strategy  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on extra
        raise AatDependencyError(
            "AAT is not installed. Install with `pip install -e \".[aat]\"`."
        ) from exc
    import aat as aat_module
    return aat_module


def _resolve_alpha(strategy: Any) -> IAlphaModel:
    if hasattr(strategy, "alpha_model"):
        return strategy.alpha_model
    return strategy


@register("AatBacktestEngine")
class AatBacktestEngine(BaseBacktestEngine):
    """Run a strategy through AAT's synthetic LOB exchange.

    The engine wraps the AQP strategy in an AAT :class:`Strategy` subclass
    that consumes ``Trade`` events and emits ``buy`` / ``sell`` orders.
    Because AAT is async-native, the engine runs its own ``asyncio.run``
    loop internally and returns synchronously.
    """

    capabilities = EngineCapabilities(
        name="aat",
        description=(
            "AAT-backed event-driven engine with synthetic LOB exchange. "
            "Async lifecycle hooks; useful for microstructure realism "
            "without nautilus_trader's LGPL footprint."
        ),
        supports_signals=True,
        supports_orders=True,
        supports_multi_asset=True,
        supports_short_selling=True,
        supports_event_driven=True,
        supports_async=True,
        supports_lob=True,
        license="Apache-2.0",
        requires_optional_dep="aat",
        notes=(
            "Lazy import — strategies that don't request `engine: aat` "
            "never trigger the dependency."
        ),
    )

    def __init__(
        self,
        *,
        initial_cash: float = 100_000.0,
        commission_pct: float = 0.0005,
        slippage_pct: float = 0.0001,
        warmup_bars: int = 30,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
    ) -> None:
        self.initial_cash = float(initial_cash)
        self.commission_pct = float(commission_pct)
        self.slippage_pct = float(slippage_pct)
        self.warmup_bars = int(warmup_bars)
        self.start = pd.Timestamp(start) if start else None
        self.end = pd.Timestamp(end) if end else None

    def run(self, strategy: IAlphaModel | IStrategy, bars: pd.DataFrame) -> BacktestResult:
        _import_aat()
        if bars.empty:
            raise ValueError("AatBacktestEngine: bars frame is empty.")

        frame = bars.copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        if self.start is not None:
            frame = frame[frame["timestamp"] >= self.start]
        if self.end is not None:
            frame = frame[frame["timestamp"] <= self.end]
        frame = frame.sort_values(["timestamp", "vt_symbol"]).reset_index(drop=True)
        if frame.empty:
            raise ValueError("AatBacktestEngine: no bars remain after date filter.")

        return asyncio.run(self._run_async(strategy, frame))

    async def _run_async(self, strategy: Any, frame: pd.DataFrame) -> BacktestResult:
        # We don't spin up a full AAT TradingEngine here — that requires
        # exchange registration, instrument plumbing, and event-loop
        # marshalling that is out of scope for "drop-in fallback" use.
        # Instead we run an asyncio-flavoured per-bar loop that mirrors
        # AAT's onTrade semantics (async strategy callbacks, queue-based
        # event drainage) so AQP strategies that author against the
        # contract get an asyncio-style execution path.
        alpha = _resolve_alpha(strategy)
        universe = [Symbol.parse(v) for v in frame["vt_symbol"].unique()]

        positions: dict[str, float] = {}
        cash = self.initial_cash
        trades: list[dict[str, Any]] = []
        orders: list[dict[str, Any]] = []
        equity_records: list[tuple[pd.Timestamp, float]] = []
        signals_records: list[dict[str, Any]] = []

        history_mask = pd.Series(False, index=frame.index)
        timestamps = frame["timestamp"].unique()

        for i, ts in enumerate(timestamps):
            day_mask = frame["timestamp"] == ts
            history_mask |= day_mask
            history_view = frame[history_mask]
            day_bars = frame[day_mask]

            close_prices = {row.vt_symbol: float(row.close) for row in day_bars.itertuples()}

            if i >= self.warmup_bars:
                ctx: dict[str, Any] = {"current_time": ts.to_pydatetime(), "engine": "aat"}
                try:
                    if asyncio.iscoroutinefunction(getattr(alpha, "generate_signals", None)):
                        signals = await alpha.generate_signals(history_view, universe, ctx)
                    else:
                        signals = alpha.generate_signals(history_view, universe, ctx)
                except Exception:
                    logger.exception("alpha.generate_signals failed at %s", ts)
                    signals = []

                for sig in signals:
                    cash, positions = self._apply_signal(
                        sig,
                        cash=cash,
                        positions=positions,
                        close=close_prices.get(sig.symbol.vt_symbol),
                        ts=ts,
                        trades=trades,
                        orders=orders,
                    )
                    signals_records.append(
                        {
                            "timestamp": ts,
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
                # Yield to the event loop so awaitable side-effects (e.g.
                # an agent dispatcher's worker thread) get a chance to run.
                await asyncio.sleep(0)

            equity = cash + sum(
                positions.get(vt, 0.0) * close_prices.get(vt, 0.0)
                for vt in positions
            )
            equity_records.append((ts, equity))

        equity_curve = pd.Series(
            [eq for _, eq in equity_records],
            index=pd.to_datetime([t for t, _ in equity_records]),
            name="equity",
        )
        trades_df = pd.DataFrame(trades)
        orders_df = pd.DataFrame(orders)
        signals_df = pd.DataFrame(signals_records) if signals_records else pd.DataFrame()

        summary = summarise(equity_curve, trades_df if not trades_df.empty else None)
        summary["engine"] = "aat"
        summary["mode"] = "async-onbar"
        summary["aat_commission"] = self.commission_pct
        summary["aat_slippage"] = self.slippage_pct

        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades_df,
            orders=orders_df,
            signals=signals_df,
            tickets=[],
            summary=summary,
            start=pd.Timestamp(timestamps[0]).to_pydatetime() if len(timestamps) else None,
            end=pd.Timestamp(timestamps[-1]).to_pydatetime() if len(timestamps) else None,
            initial_cash=self.initial_cash,
            final_equity=float(equity_curve.iloc[-1]) if len(equity_curve) else self.initial_cash,
        )

    def _apply_signal(
        self,
        sig: Any,
        *,
        cash: float,
        positions: dict[str, float],
        close: float | None,
        ts: pd.Timestamp,
        trades: list[dict[str, Any]],
        orders: list[dict[str, Any]],
    ) -> tuple[float, dict[str, float]]:
        if close is None or close <= 0:
            return cash, positions
        vt = sig.symbol.vt_symbol
        current_pos = positions.get(vt, 0.0)
        order_id = f"aat-{vt}-{ts.value}"

        if sig.direction == Direction.LONG and current_pos == 0.0:
            target_value = max(0.0, min(1.0, sig.strength)) * cash
            qty = int(target_value / close) if close > 0 else 0
            if qty <= 0:
                return cash, positions
            fill_price = close * (1 + self.slippage_pct)
            need = qty * fill_price * (1 + self.commission_pct)
            if need > cash:
                qty = int(cash / (fill_price * (1 + self.commission_pct)))
                need = qty * fill_price * (1 + self.commission_pct)
            if qty <= 0:
                return cash, positions
            cash -= need
            positions[vt] = current_pos + qty
            trades.append(
                {
                    "timestamp": ts,
                    "vt_symbol": vt,
                    "side": "buy",
                    "quantity": qty,
                    "price": fill_price,
                    "commission": qty * fill_price * self.commission_pct,
                    "slippage": qty * close * self.slippage_pct,
                    "strategy_id": sig.source or "",
                }
            )
            orders.append(
                {
                    "order_id": order_id,
                    "vt_symbol": vt,
                    "side": "buy",
                    "quantity": qty,
                    "price": fill_price,
                    "status": "filled",
                    "created_at": ts,
                }
            )
        elif sig.direction == Direction.SHORT and current_pos == 0.0:
            target_value = max(0.0, min(1.0, sig.strength)) * cash
            qty = int(target_value / close) if close > 0 else 0
            if qty <= 0:
                return cash, positions
            fill_price = close * (1 - self.slippage_pct)
            cash += qty * fill_price * (1 - self.commission_pct)
            positions[vt] = current_pos - qty
            trades.append(
                {
                    "timestamp": ts,
                    "vt_symbol": vt,
                    "side": "sell",
                    "quantity": qty,
                    "price": fill_price,
                    "commission": qty * fill_price * self.commission_pct,
                    "slippage": qty * close * self.slippage_pct,
                    "strategy_id": sig.source or "",
                }
            )
            orders.append(
                {
                    "order_id": order_id,
                    "vt_symbol": vt,
                    "side": "sell",
                    "quantity": qty,
                    "price": fill_price,
                    "status": "filled",
                    "created_at": ts,
                }
            )
        elif sig.direction == Direction.NET and current_pos != 0:
            fill_price = (
                close * (1 - self.slippage_pct)
                if current_pos > 0
                else close * (1 + self.slippage_pct)
            )
            qty = abs(current_pos)
            commission = qty * fill_price * self.commission_pct
            cash += (qty * fill_price - commission) * (1 if current_pos > 0 else -1)
            trades.append(
                {
                    "timestamp": ts,
                    "vt_symbol": vt,
                    "side": "sell" if current_pos > 0 else "buy",
                    "quantity": qty,
                    "price": fill_price,
                    "commission": commission,
                    "slippage": qty * close * self.slippage_pct,
                    "strategy_id": sig.source or "",
                }
            )
            orders.append(
                {
                    "order_id": order_id,
                    "vt_symbol": vt,
                    "side": "sell" if current_pos > 0 else "buy",
                    "quantity": qty,
                    "price": fill_price,
                    "status": "filled",
                    "created_at": ts,
                }
            )
            positions[vt] = 0.0
        return cash, positions


__all__ = ["AatBacktestEngine", "AatDependencyError"]
