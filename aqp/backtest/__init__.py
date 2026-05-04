"""Backtest engines — vectorbt-pro primary, event-driven per-bar, fallbacks.

Interchangeable engines registered so a YAML ``backtest:`` block can dispatch
via the ``engine`` key:

- ``VectorbtProEngine`` (``vbt-pro`` / ``primary``) — **primary** vectorised
  engine. Five modes (``signals``/``orders``/``optimizer``/``holding``/``random``).
- ``EventDrivenBacktester`` (``event`` / ``default``) — Lean-style per-bar
  Python loop. Used for true async agent dispatch via the strategy
  ``context['agents']`` dispatcher.
- ``VectorbtEngine`` (``vectorbt`` / ``vbt``) — OSS vectorbt fallback.
- ``BacktestingPyEngine`` (``backtesting`` / ``bt``) — single-symbol adapter
  with grid + SAMBO parameter optimisation.
- ``ZvtBacktestEngine`` (``zvt``) — Chinese-market data fallback (lazy).
- ``AatBacktestEngine`` (``aat``) — async / synthetic LOB fallback (lazy).
- ``FallbackBacktestEngine`` (``fallback`` / ``cascade``) — primary plus a
  configurable fallback chain (default: event → aat → zvt → vectorbt).

Every concrete engine inherits from :class:`aqp.backtest.base.BaseBacktestEngine`
and declares its feature surface via :class:`EngineCapabilities`. Optional
engines import their heavy runtime deps lazily.
"""
from __future__ import annotations

import contextlib

from aqp.backtest.base import BaseBacktestEngine, engine_capabilities_index
from aqp.backtest.broker_sim import SimulatedBrokerage
from aqp.backtest.capabilities import EngineCapabilities
from aqp.backtest.engine import BacktestResult, EventDrivenBacktester
from aqp.backtest.fallback_engine import (
    DEFAULT_FALLBACK_CHAIN,
    FallbackBacktestEngine,
)
from aqp.backtest.metrics import (
    indicator_analysis,
    max_drawdown,
    plot_drawdown,
    plot_equity_curve,
    plot_returns_histogram,
    risk_analysis,
    sharpe_ratio,
    sortino_ratio,
    summarise,
    turnover_report,
)
from aqp.backtest.monte_carlo import run_monte_carlo
from aqp.backtest.replay import diff_event_logs, replay_event_log
from aqp.backtest.runner import run_backtest_from_config
from aqp.backtest.vectorized import vector_backtest
from aqp.backtest.walk_forward import run_walk_forward

# Optional engine adapters — only importable if their extras are installed.
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.backtest.vectorbt_engine import VectorbtEngine  # noqa: F401
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.backtest.vectorbtpro_engine import VectorbtProEngine  # noqa: F401
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.backtest.bt_engine import BacktestingPyEngine  # noqa: F401
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.backtest.zvt_engine import ZvtBacktestEngine  # noqa: F401
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.backtest.aat_engine import AatBacktestEngine  # noqa: F401

__all__ = [
    "BacktestResult",
    "BaseBacktestEngine",
    "DEFAULT_FALLBACK_CHAIN",
    "EngineCapabilities",
    "EventDrivenBacktester",
    "FallbackBacktestEngine",
    "SimulatedBrokerage",
    "diff_event_logs",
    "engine_capabilities_index",
    "indicator_analysis",
    "max_drawdown",
    "plot_drawdown",
    "plot_equity_curve",
    "plot_returns_histogram",
    "replay_event_log",
    "risk_analysis",
    "run_backtest_from_config",
    "run_monte_carlo",
    "run_walk_forward",
    "sharpe_ratio",
    "sortino_ratio",
    "summarise",
    "turnover_report",
    "vector_backtest",
]
