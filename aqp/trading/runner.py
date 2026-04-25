"""Config-driven paper trading entry point.

Mirrors :mod:`aqp.backtest.runner` but builds an async :class:`PaperTradingSession`.
Used by::

- the ``aqp paper run`` CLI command;
- the ``run_paper`` Celery task;
- and :func:`run_paper_session_from_config` which wraps both in a single
  synchronous helper for tests.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any

import pandas as pd

from aqp.backtest.broker_sim import SimulatedBrokerage
from aqp.config import settings
from aqp.core.registry import build_from_config
from aqp.core.types import Symbol
from aqp.data.duckdb_engine import DuckDBHistoryProvider
from aqp.risk.limits import RiskLimits
from aqp.risk.manager import RiskManager
from aqp.trading.clock import RealTimeClock, SimulatedReplayClock
from aqp.trading.feeds.base import DeterministicReplayFeed
from aqp.trading.session import (
    PaperSessionConfig,
    PaperSessionResult,
    PaperTradingSession,
)

logger = logging.getLogger(__name__)


def _coerce_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    return []


def _universe_from_cfg(cfg: dict[str, Any]) -> list[Symbol]:
    session_cfg = cfg.get("session", {}) or {}
    explicit = _coerce_list(session_cfg.get("universe"))
    if explicit:
        return [Symbol.parse(t) if "." in t else Symbol(ticker=t) for t in explicit]

    strategy_cfg = cfg.get("strategy", {}) or {}
    kwargs = strategy_cfg.get("kwargs", {}) or {}
    uni_cfg = kwargs.get("universe_model", {}) or {}
    tickers = _coerce_list((uni_cfg.get("kwargs") or {}).get("symbols", [])) or settings.universe_list
    return [Symbol.parse(t) if "." in t else Symbol(ticker=t) for t in tickers]


def _risk_from_cfg(cfg: dict[str, Any]) -> RiskManager:
    risk_cfg = cfg.get("risk") or {}
    if not risk_cfg:
        return RiskManager()
    limits = RiskLimits(
        max_position_pct=float(risk_cfg.get("max_position_pct", settings.risk_max_position_pct)),
        max_daily_loss_pct=float(risk_cfg.get("max_daily_loss_pct", settings.risk_max_daily_loss_pct)),
        max_drawdown_pct=float(risk_cfg.get("max_drawdown_pct", settings.risk_max_drawdown_pct)),
        max_concentration_pct=float(risk_cfg.get("max_concentration_pct", 0.3)),
        max_gross_exposure=float(risk_cfg.get("max_gross_exposure", 1.0)),
    )
    return RiskManager(limits)


def _session_config(cfg: dict[str, Any]) -> PaperSessionConfig:
    s = cfg.get("session", {}) or {}
    return PaperSessionConfig(
        run_name=str(s.get("run_name", "paper-adhoc")),
        heartbeat_seconds=int(s.get("heartbeat_seconds", settings.paper_default_heartbeat_seconds)),
        state_flush_every_bars=int(
            s.get("state_flush_every_bars", settings.paper_state_flush_every_bars)
        ),
        history_window_bars=int(s.get("history_window_bars", 500)),
        max_bars=(int(s["max_bars"]) if s.get("max_bars") is not None else None),
        initial_cash=float(s.get("initial_cash", 100000.0)),
        stop_on_kill_switch=bool(s.get("stop_on_kill_switch", True)),
        dry_run=bool(s.get("dry_run", False)),
    )


def _default_module_paths() -> dict[str, str]:
    """Map known class names to canonical module paths."""
    return {
        "SimulatedBrokerage": "aqp.backtest.broker_sim",
        "AlpacaBrokerage": "aqp.trading.brokerages.alpaca",
        "InteractiveBrokersBrokerage": "aqp.trading.brokerages.ibkr",
        "TradierBrokerage": "aqp.trading.brokerages.tradier",
        "AlpacaDataFeed": "aqp.trading.feeds.alpaca_feed",
        "IBKRDataFeed": "aqp.trading.feeds.ibkr_feed",
        "RestPollingFeed": "aqp.trading.feeds.rest_poll",
        "DeterministicReplayFeed": "aqp.trading.feeds.base",
        "FrameworkAlgorithm": "aqp.strategies.framework",
    }


def _resolve_build(cfg: dict[str, Any]) -> Any:
    """``build_from_config`` with sensible ``module_path`` defaults."""
    if not isinstance(cfg, dict) or "class" not in cfg:
        return cfg
    cfg = dict(cfg)
    if "module_path" not in cfg:
        defaults = _default_module_paths()
        if cfg["class"] in defaults:
            cfg["module_path"] = defaults[cfg["class"]]
    return build_from_config(cfg)


def _load_dry_run_bars(universe: list[Symbol]) -> pd.DataFrame:
    provider = DuckDBHistoryProvider()
    start = pd.Timestamp(settings.default_start)
    end = pd.Timestamp(settings.default_end)
    return provider.get_bars(universe, start=start, end=end)


def build_session_from_config(
    cfg: dict[str, Any],
    *,
    task_id: str | None = None,
) -> PaperTradingSession:
    """Construct a :class:`PaperTradingSession` from a plain config dict."""
    session_cfg = _session_config(cfg)
    universe = _universe_from_cfg(cfg)

    strategy_cfg = cfg.get("strategy")
    if not strategy_cfg:
        raise ValueError("paper config must have a 'strategy' block")
    strategy = _resolve_build(strategy_cfg)

    # Brokerage: dry-run always forces the simulator; otherwise respect config.
    if session_cfg.dry_run:
        brokerage = SimulatedBrokerage(initial_cash=session_cfg.initial_cash)
    else:
        brokerage_cfg = cfg.get("brokerage")
        if brokerage_cfg is None:
            brokerage = SimulatedBrokerage(initial_cash=session_cfg.initial_cash)
        else:
            brokerage = _resolve_build(brokerage_cfg)

    # Feed: dry-run synthesises a DeterministicReplayFeed from the parquet lake.
    feed_cfg = cfg.get("feed")
    if session_cfg.dry_run or feed_cfg is None:
        bars = _load_dry_run_bars(universe)
        if bars.empty:
            raise RuntimeError(
                "Dry-run paper session requires the local parquet lake; run `make ingest` first."
            )
        feed = DeterministicReplayFeed(bars=bars, cadence_seconds=0.0)
    else:
        feed = _resolve_build(feed_cfg)

    clock = SimulatedReplayClock() if session_cfg.dry_run else RealTimeClock()
    risk = _risk_from_cfg(cfg)

    session = PaperTradingSession(
        strategy=strategy,
        brokerage=brokerage,
        feed=feed,
        risk=risk,
        clock=clock,
        config=session_cfg,
        task_id=task_id,
    )
    # The session will call ``feed.subscribe`` in its own event loop during
    # ``_connect``; we just record the desired universe on the session so the
    # connection step knows which symbols to request.
    session.pending_universe = universe  # type: ignore[attr-defined]
    return session


async def run_paper_session_from_config_async(
    cfg: dict[str, Any],
    run_name: str | None = None,
    task_id: str | None = None,
) -> PaperSessionResult:
    """Async variant — the preferred entry point from inside async code."""
    if run_name:
        cfg = dict(cfg)
        cfg.setdefault("session", {})
        cfg["session"] = {**cfg["session"], "run_name": run_name}
    session = build_session_from_config(cfg, task_id=task_id)
    return await session.run()


def run_paper_session_from_config(
    cfg: dict[str, Any],
    run_name: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Blocking entry point used by Celery tasks and the CLI."""
    result = asyncio.run(
        run_paper_session_from_config_async(cfg, run_name=run_name, task_id=task_id)
    )
    return asdict(result)
