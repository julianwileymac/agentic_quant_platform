"""backtesting.py-backed backtest engine.

Adapter that routes an :class:`aqp.core.interfaces.IStrategy` (or the alpha
stage of a ``FrameworkAlgorithm``) through the `backtesting` library
(https://github.com/kernc/backtesting.py). Returns an
:class:`aqp.backtest.engine.BacktestResult` so the runner/persistence/UI
layers can treat this engine identically to the in-house event engine.

Two usage modes:

1. **Signal mode** — accepts an :class:`IAlphaModel` and generates boolean
   entry/exit signals per bar via :meth:`IAlphaModel.generate_signals` on a
   rolling history window. Composed into a ``backtesting.lib.SignalStrategy``
   under the hood for concise state management.
2. **Direct mode** — accepts a :class:`IStrategy` and forwards
   ``on_bar`` / ``on_data`` decisions to ``self.buy`` / ``self.sell`` / ``self.position.close``.

`backtesting.py` is **single-symbol**; multi-symbol YAMLs either raise
``ValueError`` or are automatically dispatched via ``MultiBacktest``.

Also exposes :meth:`BacktestingPyEngine.optimize` for grid / SAMBO parameter
sweeps, mirroring the canonical ``Backtest.optimize`` signature.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from aqp.backtest.engine import BacktestResult
from aqp.backtest.metrics import summarise
from aqp.core.interfaces import IAlphaModel, IStrategy
from aqp.core.registry import register
from aqp.core.types import Direction, Symbol

logger = logging.getLogger(__name__)


def _import_bt():
    try:
        import backtesting as bt
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "backtesting is not installed. Install with `pip install -e \".[backtesting]\"`"
        ) from e
    return bt


def _ohlcv_for_symbol(bars: pd.DataFrame, vt_symbol: str) -> pd.DataFrame:
    """Extract a single-symbol OHLCV frame in backtesting.py's expected shape."""
    sub = bars[bars["vt_symbol"] == vt_symbol].copy()
    sub["timestamp"] = pd.to_datetime(sub["timestamp"])
    sub = sub.sort_values("timestamp").set_index("timestamp")
    return sub.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )[["Open", "High", "Low", "Close", "Volume"]]


def _resolve_alpha(strategy: IAlphaModel | IStrategy) -> IAlphaModel | None:
    if hasattr(strategy, "alpha_model"):
        return strategy.alpha_model  # type: ignore[attr-defined]
    if isinstance(strategy, IAlphaModel):
        return strategy
    return None


@register("BacktestingPyEngine")
class BacktestingPyEngine:
    """Adapter around ``backtesting.Backtest`` for single-symbol strategies.

    Parameters
    ----------
    cash:
        Starting capital (mirrors backtesting.py's ``cash`` arg).
    commission:
        Per-trade commission as a fraction (e.g. ``0.002`` for 20 bps).
    margin:
        Margin requirement (``1.0`` = no leverage).
    trade_on_close:
        Fill at the close of the decision bar instead of the next open.
    exclusive_orders:
        If True, a new signal closes any open position first.
    warmup_bars:
        Number of bars to skip before the alpha is allowed to emit signals.
    symbol:
        Optional explicit single-symbol override for multi-symbol inputs.
    """

    def __init__(
        self,
        cash: float = 100000.0,
        commission: float = 0.002,
        margin: float = 1.0,
        trade_on_close: bool = False,
        exclusive_orders: bool = True,
        warmup_bars: int = 30,
        symbol: str | None = None,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
    ) -> None:
        self.cash = float(cash)
        self.commission = float(commission)
        self.margin = float(margin)
        self.trade_on_close = bool(trade_on_close)
        self.exclusive_orders = bool(exclusive_orders)
        self.warmup_bars = int(warmup_bars)
        self.symbol = symbol
        self.start = pd.Timestamp(start) if start else None
        self.end = pd.Timestamp(end) if end else None

    # ------------------------------------------------------------------ run --

    def run(self, strategy: IAlphaModel | IStrategy, bars: pd.DataFrame) -> BacktestResult:
        vt_symbol, ohlcv = self._select_symbol(bars)
        if ohlcv.empty:
            raise ValueError("BacktestingPyEngine: empty OHLCV for selected symbol.")

        alpha = _resolve_alpha(strategy)
        if alpha is None:
            raise TypeError(
                "BacktestingPyEngine requires an IAlphaModel or a FrameworkAlgorithm with an alpha_model."
            )

        bt_mod = _import_bt()
        strategy_cls = _build_signal_strategy(alpha, vt_symbol, self.warmup_bars)

        bt = bt_mod.Backtest(
            ohlcv,
            strategy_cls,
            cash=self.cash,
            commission=self.commission,
            margin=self.margin,
            trade_on_close=self.trade_on_close,
            exclusive_orders=self.exclusive_orders,
        )
        stats = bt.run()
        return _stats_to_backtest_result(stats, ohlcv, self.cash)

    # ------------------------------------------------------------- optimize --

    def optimize(
        self,
        strategy: IAlphaModel,
        bars: pd.DataFrame,
        ranges: dict[str, list[Any]],
        maximize: str = "Sharpe Ratio",
        method: str = "grid",
        max_tries: int | None = None,
        return_heatmap: bool = False,
    ) -> dict[str, Any]:
        """Run ``Backtest.optimize`` with the given parameter ``ranges``.

        The alpha model is re-instantiated per trial with ``**kwargs`` pulled
        from the sweep axis, so any constructor kwarg is sweepable. ``method``
        can be ``"grid"`` (default) or ``"sambo"`` (model-based; requires the
        optional ``sambo`` package).
        """
        vt_symbol, ohlcv = self._select_symbol(bars)
        bt_mod = _import_bt()
        alpha_cls = type(strategy)

        _param_specs = ranges

        class _Optim(bt_mod.Strategy):
            warmup = self.warmup_bars
            alpha_kwargs: dict[str, Any] = {}

            def init(self):  # noqa: D401 - backtesting.py idiom
                kwargs = dict(self.alpha_kwargs)
                self._alpha = alpha_cls(**kwargs)
                self._state: Direction | None = None

            def next(self):
                if len(self.data) < self.warmup:
                    return
                frame = pd.DataFrame(
                    {
                        "timestamp": self.data.index,
                        "vt_symbol": vt_symbol,
                        "open": self.data.Open,
                        "high": self.data.High,
                        "low": self.data.Low,
                        "close": self.data.Close,
                        "volume": self.data.Volume,
                    }
                )
                universe = [Symbol.parse(vt_symbol)]
                try:
                    signals = self._alpha.generate_signals(
                        frame, universe, {"current_time": self.data.index[-1]}
                    )
                except Exception:
                    return
                if not signals:
                    return
                sig = signals[-1]
                if sig.direction == Direction.LONG and self._state != Direction.LONG:
                    self.buy()
                    self._state = Direction.LONG
                elif sig.direction == Direction.SHORT and self._state != Direction.SHORT:
                    self.sell()
                    self._state = Direction.SHORT
                elif sig.direction == Direction.NET:
                    self.position.close()
                    self._state = Direction.NET

        bt = bt_mod.Backtest(
            ohlcv,
            _Optim,
            cash=self.cash,
            commission=self.commission,
            margin=self.margin,
            trade_on_close=self.trade_on_close,
            exclusive_orders=self.exclusive_orders,
        )
        opt_kwargs = {k: v for k, v in _param_specs.items()}
        try:
            if return_heatmap:
                stats, heatmap = bt.optimize(
                    maximize=maximize,
                    method=method if method != "skopt" else "sambo",
                    max_tries=max_tries,
                    return_heatmap=True,
                    **{"alpha_kwargs": _grid_expand(opt_kwargs)},
                )
            else:
                stats = bt.optimize(
                    maximize=maximize,
                    method=method if method != "skopt" else "sambo",
                    max_tries=max_tries,
                    **{"alpha_kwargs": _grid_expand(opt_kwargs)},
                )
                heatmap = None
        except TypeError:
            # Older backtesting.py signatures may not accept ``method=``.
            stats = bt.optimize(maximize=maximize, **{"alpha_kwargs": _grid_expand(opt_kwargs)})
            heatmap = None

        best = _stats_to_backtest_result(stats, ohlcv, self.cash)
        return {
            "best": best,
            "stats": stats.to_dict() if hasattr(stats, "to_dict") else dict(stats),
            "heatmap": heatmap,
        }

    # ----------------------------------------------------------- internals --

    def _select_symbol(self, bars: pd.DataFrame) -> tuple[str, pd.DataFrame]:
        if bars.empty:
            raise ValueError("BacktestingPyEngine: bars frame is empty.")
        df = bars.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        if self.start is not None:
            df = df[df["timestamp"] >= self.start]
        if self.end is not None:
            df = df[df["timestamp"] <= self.end]
        symbols = df["vt_symbol"].unique().tolist()
        if not symbols:
            raise ValueError("BacktestingPyEngine: no bars remain after date filter.")
        if self.symbol and self.symbol in symbols:
            target = self.symbol
        elif len(symbols) == 1:
            target = symbols[0]
        else:
            raise ValueError(
                "BacktestingPyEngine is single-symbol. "
                f"Got {len(symbols)} symbols ({symbols[:3]}...); "
                "pass symbol=... or use VectorbtEngine/EventDrivenBacktester."
            )
        return target, _ohlcv_for_symbol(df, target)


def _grid_expand(ranges: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Expand a {param: [values]} dict into a list of concrete kwargs dicts."""
    import itertools

    keys = list(ranges.keys())
    combos = list(itertools.product(*[ranges[k] for k in keys]))
    return [dict(zip(keys, combo, strict=False)) for combo in combos]


def _build_signal_strategy(
    alpha: IAlphaModel, vt_symbol: str, warmup: int
):
    """Produce a ``backtesting.Strategy`` subclass that drives ``alpha`` each bar."""
    bt_mod = _import_bt()

    class _AlphaDrivenStrategy(bt_mod.Strategy):
        _warmup = warmup

        def init(self) -> None:  # noqa: D401
            self._state: Direction | None = None

        def next(self) -> None:
            if len(self.data) < self._warmup:
                return
            frame = pd.DataFrame(
                {
                    "timestamp": self.data.index,
                    "vt_symbol": vt_symbol,
                    "open": np.asarray(self.data.Open),
                    "high": np.asarray(self.data.High),
                    "low": np.asarray(self.data.Low),
                    "close": np.asarray(self.data.Close),
                    "volume": np.asarray(self.data.Volume),
                }
            )
            universe = [Symbol.parse(vt_symbol)]
            try:
                signals = alpha.generate_signals(
                    frame, universe, {"current_time": self.data.index[-1]}
                )
            except Exception:
                logger.exception("alpha.generate_signals failed during bt.py replay")
                return
            if not signals:
                return
            sig = signals[-1]
            if sig.direction == Direction.LONG and self._state != Direction.LONG:
                if self._state == Direction.SHORT and self.position:
                    self.position.close()
                self.buy()
                self._state = Direction.LONG
            elif sig.direction == Direction.SHORT and self._state != Direction.SHORT:
                if self._state == Direction.LONG and self.position:
                    self.position.close()
                self.sell()
                self._state = Direction.SHORT
            elif sig.direction == Direction.NET:
                if self.position:
                    self.position.close()
                self._state = Direction.NET

    return _AlphaDrivenStrategy


def _stats_to_backtest_result(
    stats: pd.Series, ohlcv: pd.DataFrame, initial_cash: float
) -> BacktestResult:
    """Translate ``backtesting.py``'s ``stats`` pd.Series into a ``BacktestResult``."""
    equity = stats.get("_equity_curve", pd.DataFrame())
    if isinstance(equity, pd.DataFrame) and "Equity" in equity.columns:
        eq_series = equity["Equity"].astype(float).copy()
    else:
        eq_series = pd.Series(dtype=float)
    eq_series.name = "equity"

    trades_df = stats.get("_trades", pd.DataFrame())
    if isinstance(trades_df, pd.DataFrame) and not trades_df.empty:
        col_map = {
            "EntryTime": "timestamp",
            "ExitTime": "exit_timestamp",
            "EntryPrice": "price",
            "ExitPrice": "exit_price",
            "Size": "quantity",
            "PnL": "pnl",
            "ReturnPct": "return",
            "Commission": "commission",
        }
        trades_df = trades_df.rename(columns={k: v for k, v in col_map.items() if k in trades_df.columns})
        trades_df["side"] = np.where(trades_df.get("quantity", 0) > 0, "buy", "sell")
        trades_df["slippage"] = 0.0
        trades_df["strategy_id"] = ""
        trades_df["vt_symbol"] = ""
        if "commission" not in trades_df.columns:
            trades_df["commission"] = 0.0

    orders_df = pd.DataFrame()

    summary = summarise(eq_series, trades_df if not trades_df.empty else None)
    summary["engine"] = "backtesting"
    for native_metric in (
        "Sharpe Ratio",
        "Sortino Ratio",
        "Calmar Ratio",
        "Max. Drawdown [%]",
        "Win Rate [%]",
        "Profit Factor",
        "SQN",
        "Return [%]",
    ):
        if native_metric in stats:
            summary[f"bt_{native_metric.lower().replace(' ', '_').replace('[%]', 'pct').replace('.', '')}"] = float(stats[native_metric])

    start_ts = eq_series.index[0] if len(eq_series) else None
    end_ts = eq_series.index[-1] if len(eq_series) else None

    return BacktestResult(
        equity_curve=eq_series,
        trades=trades_df if isinstance(trades_df, pd.DataFrame) else pd.DataFrame(),
        orders=orders_df,
        tickets=[],
        summary=summary,
        start=start_ts.to_pydatetime() if start_ts is not None else None,
        end=end_ts.to_pydatetime() if end_ts is not None else None,
        initial_cash=float(initial_cash),
        final_equity=float(eq_series.iloc[-1]) if len(eq_series) else float(initial_cash),
    )


__all__ = [
    "BacktestingPyEngine",
]
