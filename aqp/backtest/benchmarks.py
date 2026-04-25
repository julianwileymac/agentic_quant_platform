"""Benchmark helpers for backtest reports.

Two public entry points:

- :func:`fetch_benchmark` — pull daily returns for a named benchmark
  (``SPY`` / ``VOO`` / ``QQQ`` / ``DIA``) via yfinance. Results are
  cached in-memory to keep repeated backtests cheap.
- :func:`compare` — align an equity curve to a benchmark's returns and
  compute alpha, beta, information ratio, tracking error, correlation.
  Optionally returns a Plotly figure overlaying both.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


BENCHMARKS: dict[str, str] = {
    "SPY": "SPY",
    "VOO": "VOO",
    "QQQ": "QQQ",
    "DIA": "DIA",
    "IWM": "IWM",
}


@lru_cache(maxsize=32)
def fetch_benchmark(
    ticker: str,
    start: str,
    end: str,
) -> pd.Series:
    """Return a daily returns :class:`pd.Series` indexed by date.

    Uses yfinance under the hood; caches per ``(ticker, start, end)``
    triple. Returns an empty series when yfinance / the network fails so
    callers can surface a friendly "benchmark unavailable" rather than
    crashing the backtest.
    """
    symbol = BENCHMARKS.get(ticker.upper(), ticker.upper())
    try:
        import yfinance as yf
    except ImportError:  # pragma: no cover
        logger.warning("yfinance not installed; fetch_benchmark returns empty")
        return pd.Series(dtype=float)
    try:
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=False)
    except Exception as exc:
        logger.warning("yfinance benchmark fetch failed for %s: %s", symbol, exc)
        return pd.Series(dtype=float)
    if df is None or df.empty or "Adj Close" not in df.columns:
        return pd.Series(dtype=float)
    price = df["Adj Close"].copy()
    if isinstance(price, pd.DataFrame):
        price = price.iloc[:, 0]
    returns = price.pct_change().dropna()
    returns.index = pd.to_datetime(returns.index)
    return returns


@dataclass
class BenchmarkComparison:
    """Structured output of :func:`compare`."""

    alpha_annual: float
    beta: float
    correlation: float
    information_ratio: float
    tracking_error: float
    benchmark_total_return: float
    strategy_total_return: float

    def to_dict(self) -> dict[str, float]:
        return {
            "alpha_annual": self.alpha_annual,
            "beta": self.beta,
            "correlation": self.correlation,
            "information_ratio": self.information_ratio,
            "tracking_error": self.tracking_error,
            "benchmark_total_return": self.benchmark_total_return,
            "strategy_total_return": self.strategy_total_return,
        }


def compare(
    equity_curve: pd.Series,
    benchmark: str = "SPY",
    *,
    start: str | datetime | None = None,
    end: str | datetime | None = None,
) -> BenchmarkComparison:
    """Compute alpha / beta / info ratio for an equity curve vs a benchmark.

    ``equity_curve`` must be indexed by timestamp. Bumps to dollars don't
    matter — we diff to returns before aligning.
    """
    if equity_curve is None or equity_curve.empty:
        return BenchmarkComparison(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    eq = equity_curve.copy()
    eq.index = pd.to_datetime(eq.index)
    strat_returns = eq.pct_change().dropna()

    start_str = str(start or strat_returns.index.min().date())
    end_str = str(end or strat_returns.index.max().date())
    bench_returns = fetch_benchmark(benchmark, start_str, end_str)

    if bench_returns.empty:
        return BenchmarkComparison(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, float(eq.iloc[-1] / eq.iloc[0] - 1))

    joined = pd.concat([strat_returns, bench_returns], axis=1, join="inner").dropna()
    joined.columns = ["strat", "bench"]
    if joined.empty:
        return BenchmarkComparison(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, float(eq.iloc[-1] / eq.iloc[0] - 1))

    bench_std = joined["bench"].std()
    beta = 0.0
    if bench_std > 0:
        beta = float(joined["strat"].cov(joined["bench"]) / bench_std ** 2)
    correlation = float(joined["strat"].corr(joined["bench"]))

    mean_strat = joined["strat"].mean()
    mean_bench = joined["bench"].mean()
    alpha_annual = float((mean_strat - beta * mean_bench) * 252.0)
    active = joined["strat"] - joined["bench"]
    tracking_error = float(active.std() * math.sqrt(252))
    info_ratio = float((active.mean() * 252.0) / tracking_error) if tracking_error > 0 else 0.0

    strat_total = float((1.0 + joined["strat"]).prod() - 1.0)
    bench_total = float((1.0 + joined["bench"]).prod() - 1.0)

    return BenchmarkComparison(
        alpha_annual=alpha_annual,
        beta=beta,
        correlation=correlation,
        information_ratio=info_ratio,
        tracking_error=tracking_error,
        benchmark_total_return=bench_total,
        strategy_total_return=strat_total,
    )


def overlay_figure(
    equity_curve: pd.Series,
    benchmark: str = "SPY",
    *,
    title: str | None = None,
) -> Any:
    """Return a Plotly figure with equity vs benchmark cumulative returns."""
    try:
        import plotly.graph_objects as go
    except ImportError as exc:
        raise RuntimeError(
            "plotly is required to build overlay figures."
        ) from exc

    start_str = str(equity_curve.index.min().date())
    end_str = str(equity_curve.index.max().date())
    bench_returns = fetch_benchmark(benchmark, start_str, end_str)

    eq = equity_curve.copy()
    eq.index = pd.to_datetime(eq.index)
    strat_cum = eq / eq.iloc[0] - 1.0

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=strat_cum.index,
            y=strat_cum.values,
            mode="lines",
            name="Strategy",
        )
    )
    if not bench_returns.empty:
        bench_cum = (1.0 + bench_returns).cumprod() - 1.0
        fig.add_trace(
            go.Scatter(
                x=bench_cum.index,
                y=bench_cum.values,
                mode="lines",
                name=f"Benchmark ({benchmark})",
                line={"dash": "dot"},
            )
        )
    fig.update_layout(
        title=title or f"Strategy vs {benchmark}",
        yaxis_title="Cumulative return",
        xaxis_title="Date",
        hovermode="x unified",
    )
    return fig
