"""ZVT-backed backtest engine.

Adapter that runs an :class:`IAlphaModel` through ZVT's ``StockTrader`` /
``SimAccountService`` machinery, then translates the resulting account stats
into AQP's :class:`BacktestResult` shape.

ZVT is MIT-licensed and ships rich Chinese-market data and recorders, so the
engine is the natural fallback for CN equity universes. For US equities the
vbt-pro / event-driven engines remain preferable.

Lazy-imports the ``zvt`` package so AQP runs unchanged on installs without
the optional ``[zvt]`` extra.
"""
from __future__ import annotations

import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from aqp.backtest.base import BaseBacktestEngine
from aqp.backtest.capabilities import EngineCapabilities
from aqp.backtest.engine import BacktestResult
from aqp.backtest.metrics import summarise
from aqp.core.interfaces import IAlphaModel, IStrategy
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

logger = logging.getLogger(__name__)


class ZvtDependencyError(ImportError):
    """Raised when ``zvt`` is not installed but the engine is requested."""


def _import_zvt() -> Any:
    try:
        import zvt  # noqa: F401
        from zvt.contract import IntervalLevel  # noqa: F401
        from zvt.trader.sim_account import SimAccountService  # noqa: F401
        from zvt.trader.trader import StockTrader  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on extra
        raise ZvtDependencyError(
            "ZVT is not installed. Install with `pip install -e \".[zvt]\"`."
        ) from exc
    import zvt as zvt_module
    return zvt_module


def _resolve_alpha(strategy: Any) -> IAlphaModel:
    if hasattr(strategy, "alpha_model"):
        return strategy.alpha_model
    return strategy


@register("ZvtBacktestEngine")
class ZvtBacktestEngine(BaseBacktestEngine):
    """Run a strategy through ZVT's ``StockTrader``-style sim account.

    Limitations
    -----------
    ZVT prices fills at the stored bar close (plus configurable slippage and
    commission as fractions); it is not a matching engine. Use the AAT
    engine for synthetic LOB fidelity.
    """

    capabilities = EngineCapabilities(
        name="zvt",
        description=(
            "ZVT-backed bar simulator. China-market-centric data + recorders; "
            "L1 bar close fills with configurable commission + slippage."
        ),
        supports_signals=True,
        supports_multi_asset=True,
        supports_short_selling=False,
        supports_event_driven=True,
        supports_per_bar_python=True,
        cn_market_data=True,
        us_market_data=False,
        license="MIT",
        requires_optional_dep="zvt",
        notes=(
            "Lazy import — strategies that don't request `engine: zvt` "
            "never trigger the dependency."
        ),
    )

    def __init__(
        self,
        *,
        initial_cash: float = 1_000_000.0,
        buy_cost: float = 0.001,
        sell_cost: float = 0.001,
        slippage: float = 0.001,
        warmup_bars: int = 30,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        provider: str | None = None,
    ) -> None:
        self.initial_cash = float(initial_cash)
        self.buy_cost = float(buy_cost)
        self.sell_cost = float(sell_cost)
        self.slippage = float(slippage)
        self.warmup_bars = int(warmup_bars)
        self.start = pd.Timestamp(start) if start else None
        self.end = pd.Timestamp(end) if end else None
        self.provider = provider

    def run(self, strategy: IAlphaModel | IStrategy, bars: pd.DataFrame) -> BacktestResult:
        _import_zvt()
        if bars.empty:
            raise ValueError("ZvtBacktestEngine: bars frame is empty.")

        frame = bars.copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        if self.start is not None:
            frame = frame[frame["timestamp"] >= self.start]
        if self.end is not None:
            frame = frame[frame["timestamp"] <= self.end]
        frame = frame.sort_values(["timestamp", "vt_symbol"]).reset_index(drop=True)
        if frame.empty:
            raise ValueError("ZvtBacktestEngine: no bars remain after date filter.")

        # Run a simplified sim_account-style simulation in-process to avoid
        # requiring users to populate ZVT's database for every backtest.
        # When the user has a fully-configured ZVT environment they should
        # build a dedicated ``StockTrader`` subclass; this path is the
        # fallback "library-style" execution for any tidy bars frame.
        return self._run_simplified(strategy, frame)

    def _run_simplified(self, strategy: Any, frame: pd.DataFrame) -> BacktestResult:
        alpha = _resolve_alpha(strategy)
        universe = [Symbol.parse(v) for v in frame["vt_symbol"].unique()]

        positions: dict[str, float] = {}  # vt_symbol -> shares
        cash = self.initial_cash
        trades: list[dict[str, Any]] = []
        orders: list[dict[str, Any]] = []
        equity_records: list[tuple[pd.Timestamp, float]] = []
        signals_records: list[dict[str, Any]] = []

        sorted_frame = frame
        history_mask = pd.Series(False, index=sorted_frame.index)
        timestamps = sorted_frame["timestamp"].unique()

        for i, ts in enumerate(timestamps):
            day_mask = sorted_frame["timestamp"] == ts
            history_mask |= day_mask
            history_view = sorted_frame[history_mask]

            day_bars = sorted_frame[day_mask]
            close_prices = {row.vt_symbol: float(row.close) for row in day_bars.itertuples()}

            if i >= self.warmup_bars:
                ctx: dict[str, Any] = {"current_time": ts.to_pydatetime()}
                try:
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
        summary["engine"] = "zvt"
        summary["mode"] = "simplified-sim-account"
        summary["zvt_buy_cost"] = self.buy_cost
        summary["zvt_sell_cost"] = self.sell_cost
        summary["zvt_slippage"] = self.slippage

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
        sig: Signal,
        *,
        cash: float,
        positions: dict[str, float],
        close: float | None,
        ts: pd.Timestamp,
        trades: list[dict[str, Any]],
        orders: list[dict[str, Any]],
    ) -> tuple[float, dict[str, Any]]:
        if close is None or close <= 0:
            return cash, positions
        vt = sig.symbol.vt_symbol
        current_pos = positions.get(vt, 0.0)
        order_id = f"zvt-{vt}-{ts.value}"

        if sig.direction == Direction.LONG and current_pos == 0.0:
            target_value = max(0.0, min(1.0, sig.strength)) * cash
            qty = int(target_value / close) if close > 0 else 0
            if qty <= 0:
                return cash, positions
            fill_price = close * (1 + self.slippage)
            need = qty * fill_price * (1 + self.buy_cost)
            if need > cash:
                qty = int(cash / (fill_price * (1 + self.buy_cost)))
                need = qty * fill_price * (1 + self.buy_cost)
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
                    "commission": qty * fill_price * self.buy_cost,
                    "slippage": qty * close * self.slippage,
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
        elif sig.direction == Direction.NET and current_pos > 0:
            fill_price = close * (1 - self.slippage)
            proceeds = current_pos * fill_price * (1 - self.sell_cost)
            cash += proceeds
            trades.append(
                {
                    "timestamp": ts,
                    "vt_symbol": vt,
                    "side": "sell",
                    "quantity": current_pos,
                    "price": fill_price,
                    "commission": current_pos * fill_price * self.sell_cost,
                    "slippage": current_pos * close * self.slippage,
                    "strategy_id": sig.source or "",
                }
            )
            orders.append(
                {
                    "order_id": order_id,
                    "vt_symbol": vt,
                    "side": "sell",
                    "quantity": current_pos,
                    "price": fill_price,
                    "status": "filled",
                    "created_at": ts,
                }
            )
            positions[vt] = 0.0
        return cash, positions


__all__ = ["ZvtBacktestEngine", "ZvtDependencyError"]
