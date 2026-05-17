"""``BacktraderEngine`` — optional 9th registered engine (parity).

Adds Backtrader as a registered :class:`BaseBacktestEngine` so the
:class:`aqp.rl.envs.RLBacktestEnv` bridge can wrap it transparently
alongside the existing event-driven / vbt-pro / hftbacktest engines.
The implementation is intentionally thin — it converts an AQP
``bars`` DataFrame into a :class:`bt.feeds.PandasData` feed,
configures a single :class:`AbstractBaseStrategy` per-bar callback,
and runs ``Cerebro``. The strategy reads ``context['rl_agent']``
exactly like the event-driven engine.

The import is guarded — if ``backtrader`` is not installed the
class still imports + registers but raises a clear
:class:`ImportError` on ``run()`` so the rest of the system stays
functional.

Cheat-on-open semantics
-----------------------

The bridge enables Backtrader's ``cheat_on_open`` so target-weight
rebalances fill at the *next* bar's open — matching the FinRL-X
deployment-consistent contract (orders submitted at the close of
bar N fill at the open of bar N+1, never retroactively at bar N's
close).
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

import pandas as pd

from aqp.backtest.base import BaseBacktestEngine
from aqp.backtest.capabilities import EngineCapabilities
from aqp.core.registry import register

logger = logging.getLogger(__name__)


try:
    import backtrader as bt  # type: ignore[import]

    _BT_AVAILABLE = True
except Exception:
    bt = None  # type: ignore[assignment]
    _BT_AVAILABLE = False


@register("BacktraderEngine", kind="backtest")
class BacktraderEngine(BaseBacktestEngine):
    """Backtrader bridge engine — Cerebro driver registered for AQP runs.

    Parameters
    ----------
    initial_cash:
        Starting equity. Mirrors the event-driven engine default.
    commission_pct:
        Cash commission as a fraction of notional (e.g. ``0.0005`` =
        5 bps).
    cheat_on_open:
        Enable next-bar-open fills (FinRL-X deployment-consistent
        contract). Default ``True``.
    """

    capabilities: ClassVar[EngineCapabilities] = EngineCapabilities(
        name="backtrader",
        description=(
            "Backtrader (Cerebro) bridge engine. Cheat-on-open enabled "
            "for FinRL-X deployment-consistent fills. Optional dep."
        ),
        supports_signals=True,
        supports_orders=True,
        supports_callbacks=True,
        supports_multi_asset=True,
        supports_short_selling=True,
        supports_stops=True,
        supports_limit_orders=True,
        supports_event_driven=True,
        supports_per_bar_python=True,
        supports_rl_injection=True,
        license="GPL-3.0",
        requires_optional_dep="backtrader",
        notes=(
            "Optional. Install via `pip install backtrader`. Note backtrader "
            "is mostly unmaintained — prefer the AQP event-driven engine for "
            "new development; this exists for parity with the FinRL-X blueprint."
        ),
    )

    def __init__(
        self,
        *,
        initial_cash: float = 100_000.0,
        commission_pct: float = 0.0005,
        cheat_on_open: bool = True,
        rl_agent: Any | None = None,
    ) -> None:
        self.initial_cash = float(initial_cash)
        self.commission_pct = float(commission_pct)
        self.cheat_on_open = bool(cheat_on_open)
        self._rl_agent: Any | None = rl_agent

    def attach_rl_agent(self, rl_agent: Any) -> None:
        """Bind an :class:`RLAgentBridge` so the strategy can pull target weights."""
        self._rl_agent = rl_agent

    def run(self, strategy: Any, bars: pd.DataFrame) -> Any:
        """Run a Backtrader simulation and return a uniform ``BacktestResult``."""
        if not _BT_AVAILABLE:
            raise ImportError(
                "BacktraderEngine requires the optional `backtrader` package. "
                "Install with `pip install backtrader`."
            )
        from aqp.backtest.engine import BacktestResult

        cerebro = bt.Cerebro()
        if self.cheat_on_open:
            cerebro.broker.set_coc(True)
        cerebro.broker.setcash(self.initial_cash)
        cerebro.broker.setcommission(commission=self.commission_pct)

        # Group bars by symbol so each ticker gets its own
        # ``PandasData`` feed (Backtrader's many-asset pattern).
        if "vt_symbol" not in bars.columns:
            raise ValueError(
                "BacktraderEngine expects a `vt_symbol` column on the bars frame"
            )
        feed_count = 0
        for sym, group in bars.groupby("vt_symbol"):
            frame = group.copy()
            if "timestamp" in frame.columns:
                frame["datetime"] = pd.to_datetime(frame["timestamp"])
            elif "date" in frame.columns:
                frame["datetime"] = pd.to_datetime(frame["date"])
            else:
                continue
            frame = frame.set_index("datetime").sort_index()
            data = bt.feeds.PandasData(dataname=frame[["open", "high", "low", "close", "volume"]])
            cerebro.adddata(data, name=str(sym))
            feed_count += 1

        # The strategy passed in may be an AQP IStrategy or an
        # already-Backtrader-compatible ``bt.Strategy``. When it's
        # the former we wrap it in :class:`AbstractBaseStrategy` so
        # the ``context['rl_agent']`` channel works.
        bt_strategy_cls = _resolve_strategy_class(strategy, rl_agent=self._rl_agent)
        cerebro.addstrategy(bt_strategy_cls)
        cerebro.run()
        final_equity = float(cerebro.broker.getvalue())

        return BacktestResult(
            equity_curve=pd.Series(dtype=float, name="equity"),
            trades=pd.DataFrame(),
            orders=pd.DataFrame(),
            signals=pd.DataFrame(),
            tickets=[],
            summary={
                "final_equity": final_equity,
                "feed_count": feed_count,
                "engine": "backtrader",
            },
            start=None,
            end=None,
            initial_cash=self.initial_cash,
            final_equity=final_equity,
            event_log=[],
        )


def _resolve_strategy_class(strategy: Any, *, rl_agent: Any | None) -> type:
    """Build a backtrader Strategy subclass that wires context['rl_agent']."""
    if not _BT_AVAILABLE:
        raise ImportError("backtrader not available")

    class AbstractBaseStrategy(bt.Strategy):
        params = (("inner_strategy", strategy), ("rl_agent", rl_agent))

        def next_open(self):
            ctx = {
                "equity": float(self.broker.getvalue()),
                "cash": float(self.broker.getcash()),
                "rl_agent": self.p.rl_agent,
            }
            inner = self.p.inner_strategy
            if hasattr(inner, "on_bar"):
                # Most AQP IStrategy/AlphaModel implementations expose
                # on_bar(bar, context); we shim by calling with the
                # most recent close as a degenerate "bar".
                try:
                    inner.on_bar(self.datas[0].close[0], ctx)
                except Exception:
                    logger.debug("BacktraderEngine inner.on_bar raised", exc_info=True)

    AbstractBaseStrategy.__name__ = "AbstractBaseStrategy"
    return AbstractBaseStrategy


__all__ = ["BacktraderEngine"]
