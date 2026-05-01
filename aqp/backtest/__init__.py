"""Backtest engine — event-driven + vectorized + WFO + Monte Carlo.

Three interchangeable engines are exposed and registered so a YAML
``backtest:`` block can dispatch to any of them via the ``engine`` key:

- ``EventDrivenBacktester`` — default, Lean-style 5-stage pipeline replay.
- ``VectorbtEngine`` — vectorbt ``Portfolio.from_signals`` adapter (optional extra).
- ``BacktestingPyEngine`` — backtesting.py single-symbol adapter (optional extra).

The optional engines import their heavy runtime deps lazily so the base
install footprint stays unchanged.
"""
from __future__ import annotations

import contextlib

from aqp.backtest.broker_sim import SimulatedBrokerage
from aqp.backtest.engine import BacktestResult, EventDrivenBacktester
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
    from aqp.backtest.bt_engine import BacktestingPyEngine  # noqa: F401

__all__ = [
    "BacktestResult",
    "EventDrivenBacktester",
    "SimulatedBrokerage",
    "diff_event_logs",
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
