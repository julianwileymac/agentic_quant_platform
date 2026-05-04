"""Multi-mode vectorbt-pro engine.

The engine routes a strategy through one of five vbt-pro constructors based
on the ``mode`` kwarg:

- ``signals`` — wide entries/exits arrays via :func:`build_signal_arrays`,
  fed into ``Portfolio.from_signals`` with the full kwarg surface
  (``sl_stop`` / ``tsl_stop`` / ``tp_stop`` / ``leverage`` /
  ``cash_sharing`` / ``group_by`` / ``multiplier`` / ``direction`` /
  ``accumulate`` / ``size_type`` / ``price``).
- ``orders`` — wide order arrays from an :class:`IOrderModel` (via
  :func:`build_order_arrays`), fed into ``Portfolio.from_orders``.
- ``optimizer`` — a ``PortfolioOptimizer`` instance from
  :mod:`optimizer_adapter`, fed into ``Portfolio.from_optimizer``.
- ``holding`` — a buy-and-hold sanity baseline via ``Portfolio.from_holding``.
- ``random`` — random entries/exits baseline via
  ``Portfolio.from_random_signals``.

For research / hyperparameter loops use :class:`WalkForwardHarness` from
``aqp.backtest.vbtpro.wfo``; that path lives outside this engine because it
calls back into Python on every window (necessary for agents/ML), whereas
this engine sticks to a single vbt-pro simulation per ``run`` call.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.backtest.base import BaseBacktestEngine
from aqp.backtest.capabilities import EngineCapabilities
from aqp.backtest.engine import BacktestResult
from aqp.backtest.vbtpro.data_utils import (
    filter_bars,
    pivot_close,
    pivot_ohlcv,
    universe_from_bars,
)
from aqp.backtest.vbtpro.optimizer_adapter import build_portfolio_from_optimizer
from aqp.backtest.vbtpro.order_builder import OrderArrays, build_order_arrays
from aqp.backtest.vbtpro.result_mapper import portfolio_to_backtest_result
from aqp.backtest.vbtpro.signal_builder import SignalArrays, build_signal_arrays
from aqp.backtest.vectorbt_backend import import_vectorbtpro
from aqp.core.interfaces import IAlphaModel, IOrderModel, IStrategy
from aqp.core.registry import build_from_config, register

logger = logging.getLogger(__name__)


VALID_MODES = ("signals", "orders", "optimizer", "holding", "random")


@register("VectorbtProEngine")
class VectorbtProEngine(BaseBacktestEngine):
    """Deep vectorbt-pro adapter — five modes behind a single ``run`` call.

    Parameters
    ----------
    mode:
        Which vbt-pro constructor to use. One of :data:`VALID_MODES`.
    initial_cash:
        Starting capital. Forwarded as ``init_cash`` to vbt-pro.
    fees / slippage:
        Per-order frictions. Accepts scalars or wide DataFrames.
    freq:
        Frequency string fed to vbt-pro for return annualisation
        (``"1D"``, ``"1H"``, ``"15T"``, etc.).
    allow_short:
        When False, short signals from the alpha are squashed.
    cash_sharing / group_by:
        Multi-asset accounting flags forwarded to vbt-pro.
    direction:
        ``"longonly"``, ``"shortonly"``, or ``"both"``. Forwarded.
    accumulate:
        Whether vbt-pro accumulates positions across consecutive entries.
    size:
        Default position size (used when neither the alpha nor the order
        model provide one).
    size_type:
        ``"amount"`` / ``"percent"`` / ``"value"`` / ``"targetshares"`` /
        ``"targetpercent"`` / ``"targetvalue"``.
    sl_stop / tsl_stop / tp_stop:
        Stop-loss, trailing-stop, take-profit (fractional). Scalars or
        per-asset DataFrames.
    leverage / leverage_mode:
        Leverage settings forwarded to vbt-pro.
    multiplier:
        Contract multiplier (futures).
    warmup_bars:
        Bars to skip in the per-bar signal loop.
    portfolio_kwargs:
        Free-form kwargs merged into ``Portfolio.from_*`` after the
        engine-derived ones. Use this for any vbt-pro feature not exposed
        explicitly (e.g. ``call_seq``, ``staticized``, ``chunked``).
    order_model:
        Optional :class:`IOrderModel` config dict; only used when
        ``mode="orders"``.
    optimizer:
        Optional allocator config dict (e.g. an ``EqualWeightOptimizer``);
        only used when ``mode="optimizer"``.
    random_kwargs:
        Optional kwargs forwarded to ``Portfolio.from_random_signals``
        (e.g. ``n=10`` random entries, ``seed=42``).
    """

    capabilities = EngineCapabilities(
        name="vectorbt-pro",
        description=(
            "Primary vectorised engine. Five modes (signals/orders/optimizer/"
            "holding/random); full kwarg surface; rich callbacks; integrates "
            "with WalkForwardHarness for per-window agent/ML dispatch."
        ),
        supports_signals=True,
        supports_orders=True,
        supports_callbacks=True,
        supports_holding_baseline=True,
        supports_random_baseline=True,
        supports_multi_asset=True,
        supports_cash_sharing=True,
        supports_grouping=True,
        supports_short_selling=True,
        supports_leverage=True,
        supports_stops=True,
        supports_limit_orders=True,
        supports_multiplier=True,
        supports_vectorized=True,
        supports_param_sweep=True,
        supports_walk_forward=True,
        supports_optimizer=True,
        supports_indicator_factory=True,
        supports_monte_carlo=True,
        license="proprietary",
        requires_optional_dep="vectorbtpro",
        notes=(
            "Numba constraint: per-bar callbacks (signal_func_nb / "
            "order_func_nb) are JIT-only. Use precompute or "
            "WalkForwardHarness for agent/ML integration."
        ),
    )

    summary_engine = "vectorbt-pro"

    def __init__(
        self,
        *,
        mode: str = "signals",
        initial_cash: float = 100000.0,
        fees: float = 0.0005,
        slippage: float = 0.0002,
        freq: str = "1D",
        allow_short: bool = True,
        cash_sharing: bool = False,
        group_by: bool | str | list[Any] = False,
        direction: str | None = None,
        accumulate: bool = False,
        size: float | None = None,
        size_type: str | None = None,
        sl_stop: float | None = None,
        tsl_stop: float | None = None,
        tp_stop: float | None = None,
        leverage: float | None = None,
        leverage_mode: str | None = None,
        multiplier: float | None = None,
        warmup_bars: int = 30,
        record_signals: bool = True,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        portfolio_kwargs: dict[str, Any] | None = None,
        order_model: dict[str, Any] | IOrderModel | None = None,
        optimizer: dict[str, Any] | Any | None = None,
        random_kwargs: dict[str, Any] | None = None,
    ) -> None:
        if mode not in VALID_MODES:
            raise ValueError(
                f"mode must be one of {VALID_MODES}; got {mode!r}"
            )
        self.mode = mode
        self.initial_cash = float(initial_cash)
        self.fees = fees
        self.slippage = slippage
        self.freq = str(freq)
        self.allow_short = bool(allow_short)
        self.cash_sharing = bool(cash_sharing)
        self.group_by = group_by
        self.direction = direction
        self.accumulate = bool(accumulate)
        self.size = size
        self.size_type = size_type
        self.sl_stop = sl_stop
        self.tsl_stop = tsl_stop
        self.tp_stop = tp_stop
        self.leverage = leverage
        self.leverage_mode = leverage_mode
        self.multiplier = multiplier
        self.warmup_bars = int(warmup_bars)
        self.record_signals = bool(record_signals)
        self.start = pd.Timestamp(start) if start else None
        self.end = pd.Timestamp(end) if end else None
        self.portfolio_kwargs = dict(portfolio_kwargs or {})
        self._order_model_cfg = order_model
        self._optimizer_cfg = optimizer
        self.random_kwargs = dict(random_kwargs or {})

    def _import_backend(self):
        return import_vectorbtpro().module

    def run(self, strategy: IAlphaModel | IStrategy | Any, bars: pd.DataFrame) -> BacktestResult:
        if bars.empty:
            raise ValueError("VectorbtProEngine: bars frame is empty.")

        frame = filter_bars(bars, start=self.start, end=self.end)
        if frame.empty:
            raise ValueError("VectorbtProEngine: no bars remain after date filter.")

        ohlcv = pivot_ohlcv(frame)
        close = ohlcv.close

        if self.mode == "signals":
            return self._run_signals(strategy, frame, close, ohlcv=ohlcv)
        if self.mode == "orders":
            return self._run_orders(strategy, frame, close, ohlcv=ohlcv)
        if self.mode == "optimizer":
            return self._run_optimizer(close)
        if self.mode == "holding":
            return self._run_holding(close)
        if self.mode == "random":
            return self._run_random(close)
        raise AssertionError(f"unhandled mode {self.mode!r}")

    def _common_kwargs(self) -> dict[str, Any]:
        """Engine-level kwargs that are common across constructors."""
        kw: dict[str, Any] = {
            "init_cash": self.initial_cash,
            "fees": self.fees,
            "slippage": self.slippage,
            "freq": self.freq,
            "cash_sharing": self.cash_sharing,
            "group_by": self.group_by,
        }
        if self.direction is not None:
            kw["direction"] = self.direction
        if self.size is not None:
            kw["size"] = self.size
        if self.size_type is not None:
            kw["size_type"] = self.size_type
        if self.leverage is not None:
            kw["leverage"] = self.leverage
        if self.leverage_mode is not None:
            kw["leverage_mode"] = self.leverage_mode
        if self.multiplier is not None:
            kw["multiplier"] = self.multiplier
        return kw

    def _run_signals(
        self,
        strategy: Any,
        frame: pd.DataFrame,
        close: pd.DataFrame,
        *,
        ohlcv: Any,
    ) -> BacktestResult:
        signals = build_signal_arrays(
            strategy,
            bars=frame,
            close=close,
            allow_short=self.allow_short,
            warmup_bars=self.warmup_bars,
            record_signals=self.record_signals,
        )
        vbt = self._import_backend()
        kwargs = self._common_kwargs()
        kwargs.update(self.portfolio_kwargs)

        # OHLC for stop-fill realism.
        kwargs.setdefault("open", ohlcv.open)
        kwargs.setdefault("high", ohlcv.high)
        kwargs.setdefault("low", ohlcv.low)

        for stop, value in (
            ("sl_stop", self.sl_stop),
            ("tsl_stop", self.tsl_stop),
            ("tp_stop", self.tp_stop),
        ):
            if value is not None:
                kwargs[stop] = value
        if self.accumulate:
            kwargs["accumulate"] = True

        # vbt-pro extensions from SignalArrays (these override engine defaults).
        if signals.size is not None:
            kwargs["size"] = signals.size
        if signals.price is not None:
            kwargs["price"] = signals.price
        for stop_name in ("sl_stop", "tsl_stop", "tp_stop"):
            value = getattr(signals, stop_name)
            if value is not None:
                kwargs[stop_name] = value

        if signals.has_shorts():
            pf = vbt.Portfolio.from_signals(
                close=close,
                entries=signals.entries,
                exits=signals.exits,
                short_entries=signals.short_entries,
                short_exits=signals.short_exits,
                **kwargs,
            )
        else:
            pf = vbt.Portfolio.from_signals(
                close=close,
                entries=signals.entries,
                exits=signals.exits,
                **kwargs,
            )

        return portfolio_to_backtest_result(
            pf,
            close=close,
            initial_cash=self.initial_cash,
            engine=self.summary_engine,
            mode="signals",
            signal_records=signals.signal_records,
        )

    def _run_orders(
        self,
        strategy: Any,
        frame: pd.DataFrame,
        close: pd.DataFrame,
        *,
        ohlcv: Any,
    ) -> BacktestResult:
        order_model = self._resolve_order_model(strategy)
        if order_model is None:
            raise ValueError(
                "VectorbtProEngine[mode=orders] requires either an `order_model` "
                "kwarg, an order_model attribute on the strategy, or a strategy "
                "that itself implements IOrderModel."
            )
        order_arrays: OrderArrays = build_order_arrays(
            order_model,
            bars=frame,
            universe=universe_from_bars(frame),
            close=close,
        )

        vbt = self._import_backend()
        kwargs = self._common_kwargs()
        kwargs.pop("size_type", None)  # OrderArrays.size_type wins
        kwargs.update(self.portfolio_kwargs)
        kwargs.setdefault("open", ohlcv.open)
        kwargs.setdefault("high", ohlcv.high)
        kwargs.setdefault("low", ohlcv.low)
        kwargs.update(order_arrays.to_kwargs())

        pf = vbt.Portfolio.from_orders(close=close, **kwargs)
        return portfolio_to_backtest_result(
            pf,
            close=close,
            initial_cash=self.initial_cash,
            engine=self.summary_engine,
            mode="orders",
        )

    def _run_optimizer(self, close: pd.DataFrame) -> BacktestResult:
        optimizer = self._resolve_optimizer()
        if optimizer is None:
            raise ValueError(
                "VectorbtProEngine[mode=optimizer] requires an `optimizer` kwarg."
            )
        pf = build_portfolio_from_optimizer(
            optimizer,
            close=close,
            init_cash=self.initial_cash,
            fees=float(self.fees) if isinstance(self.fees, (int, float)) else 0.0,
            slippage=float(self.slippage) if isinstance(self.slippage, (int, float)) else 0.0,
            extra_kwargs={**self._common_kwargs(), **self.portfolio_kwargs},
        )
        return portfolio_to_backtest_result(
            pf,
            close=close,
            initial_cash=self.initial_cash,
            engine=self.summary_engine,
            mode="optimizer",
        )

    def _run_holding(self, close: pd.DataFrame) -> BacktestResult:
        vbt = self._import_backend()
        kwargs = self._common_kwargs()
        kwargs.update(self.portfolio_kwargs)
        pf = vbt.Portfolio.from_holding(close=close, **kwargs)
        return portfolio_to_backtest_result(
            pf,
            close=close,
            initial_cash=self.initial_cash,
            engine=self.summary_engine,
            mode="holding",
        )

    def _run_random(self, close: pd.DataFrame) -> BacktestResult:
        vbt = self._import_backend()
        kwargs = self._common_kwargs()
        kwargs.update(self.portfolio_kwargs)
        kwargs.update(self.random_kwargs)
        kwargs.setdefault("n", 10)
        pf = vbt.Portfolio.from_random_signals(close=close, **kwargs)
        return portfolio_to_backtest_result(
            pf,
            close=close,
            initial_cash=self.initial_cash,
            engine=self.summary_engine,
            mode="random",
        )

    def _resolve_order_model(self, strategy: Any) -> IOrderModel | None:
        if self._order_model_cfg is not None:
            if isinstance(self._order_model_cfg, dict):
                return build_from_config(self._order_model_cfg)
            return self._order_model_cfg  # type: ignore[return-value]
        order_attr = getattr(strategy, "order_model", None)
        if order_attr is not None:
            return order_attr
        if isinstance(strategy, IOrderModel):
            return strategy
        return None

    def _resolve_optimizer(self) -> Any | None:
        if self._optimizer_cfg is None:
            return None
        if isinstance(self._optimizer_cfg, dict):
            return build_from_config(self._optimizer_cfg)
        return self._optimizer_cfg


__all__ = ["VectorbtProEngine", "VALID_MODES"]
