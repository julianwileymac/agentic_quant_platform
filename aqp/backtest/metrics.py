"""Performance metrics + Plotly figure builders."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

logger = logging.getLogger(__name__)


def returns_from_equity(equity: pd.Series) -> pd.Series:
    return equity.pct_change().fillna(0)


def sharpe_ratio(returns: pd.Series, rf: float = 0.0, periods_per_year: int = 252) -> float:
    if returns.empty or returns.std() == 0:
        return 0.0
    excess = returns - rf / periods_per_year
    return float(np.sqrt(periods_per_year) * excess.mean() / excess.std(ddof=0))


def sortino_ratio(returns: pd.Series, rf: float = 0.0, periods_per_year: int = 252) -> float:
    if returns.empty:
        return 0.0
    excess = returns - rf / periods_per_year
    downside = excess[excess < 0]
    denom = downside.std(ddof=0)
    if denom == 0 or np.isnan(denom):
        return 0.0
    return float(np.sqrt(periods_per_year) * excess.mean() / denom)


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max
    return float(dd.min())


def calmar_ratio(equity: pd.Series, periods_per_year: int = 252) -> float:
    if equity.empty:
        return 0.0
    mdd = max_drawdown(equity)
    if mdd == 0:
        return 0.0
    total_return = equity.iloc[-1] / equity.iloc[0] - 1
    years = len(equity) / periods_per_year
    annual = (1 + total_return) ** (1 / max(years, 1e-9)) - 1
    return float(annual / abs(mdd))


def turnover(trades: pd.DataFrame, equity: pd.Series) -> float:
    if trades.empty or equity.empty:
        return 0.0
    notional = (trades["quantity"].abs() * trades["price"]).sum()
    return float(notional / equity.iloc[0])


# ---------------------------------------------------------------------------
# Rolling / benchmark-aware metrics (ML4T-style pyfolio parity)
# ---------------------------------------------------------------------------


def rolling_sharpe(
    returns: pd.Series,
    window: int = 63,
    rf: float = 0.0,
    periods_per_year: int = 252,
) -> pd.Series:
    if returns.empty:
        return pd.Series(dtype=float)
    excess = returns - rf / periods_per_year
    mean = excess.rolling(window).mean()
    std = excess.rolling(window).std(ddof=0)
    return np.sqrt(periods_per_year) * mean / std.replace(0, np.nan)


def rolling_sortino(
    returns: pd.Series,
    window: int = 63,
    rf: float = 0.0,
    periods_per_year: int = 252,
) -> pd.Series:
    if returns.empty:
        return pd.Series(dtype=float)
    excess = returns - rf / periods_per_year
    mean = excess.rolling(window).mean()
    # Downside stddev: only penalise negative returns.
    downside = excess.where(excess < 0, 0.0)
    std = downside.rolling(window).std(ddof=0)
    return np.sqrt(periods_per_year) * mean / std.replace(0, np.nan)


def rolling_beta(returns: pd.Series, benchmark: pd.Series, window: int = 63) -> pd.Series:
    if returns.empty or benchmark.empty:
        return pd.Series(dtype=float)
    aligned = pd.concat([returns, benchmark], axis=1).dropna()
    aligned.columns = ["r", "b"]
    cov = aligned["r"].rolling(window).cov(aligned["b"])
    var = aligned["b"].rolling(window).var(ddof=0)
    return cov / var.replace(0, np.nan)


def information_ratio(
    returns: pd.Series,
    benchmark: pd.Series,
    periods_per_year: int = 252,
) -> float:
    if returns.empty or benchmark.empty:
        return 0.0
    aligned = pd.concat([returns, benchmark], axis=1).dropna()
    aligned.columns = ["r", "b"]
    active = aligned["r"] - aligned["b"]
    std = active.std(ddof=0)
    if std == 0:
        return 0.0
    return float(np.sqrt(periods_per_year) * active.mean() / std)


def drawdown_series(equity: pd.Series) -> pd.Series:
    if equity.empty:
        return pd.Series(dtype=float)
    return (equity - equity.cummax()) / equity.cummax()


def drawdown_duration_days(equity: pd.Series) -> int:
    """Longest span (in rows) the equity curve spent below its peak."""
    if equity.empty:
        return 0
    dd = drawdown_series(equity)
    cur = 0
    best = 0
    for v in dd.values:
        if v < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return int(best)


def cvar(returns: pd.Series, alpha: float = 0.05) -> float:
    """Conditional Value-at-Risk at the ``alpha`` tail."""
    if returns.empty:
        return 0.0
    cutoff = returns.quantile(alpha)
    tail = returns[returns <= cutoff]
    return float(tail.mean()) if not tail.empty else 0.0


def downside_metrics(returns: pd.Series) -> dict[str, float]:
    if returns.empty:
        return {"var_5": 0.0, "cvar_5": 0.0, "downside_vol": 0.0, "skew": 0.0, "kurt": 0.0}
    neg = returns[returns < 0]
    return {
        "var_5": float(returns.quantile(0.05)),
        "cvar_5": cvar(returns, 0.05),
        "downside_vol": float(neg.std(ddof=0) * np.sqrt(252)) if not neg.empty else 0.0,
        "skew": float(returns.skew()),
        "kurt": float(returns.kurt()),
    }


def pyfolio_stats(returns: pd.Series) -> dict[str, float]:
    """Prefer ``pyfolio.timeseries.perf_stats``; fall back to our own helpers.

    The output schema matches the pyfolio summary table so the Factor
    Evaluation and Strategy Test panes can render identical-looking
    tear-sheets regardless of whether pyfolio is installed.
    """
    try:
        from pyfolio.timeseries import perf_stats  # type: ignore[import]

        frame = perf_stats(returns)
        return {str(k).lower().replace(" ", "_"): float(v) for k, v in frame.items()}
    except Exception:
        logger.debug("pyfolio unavailable; using builtin stats", exc_info=True)

    equity = (1 + returns.fillna(0)).cumprod()
    return {
        "annual_return": float(equity.iloc[-1] ** (252 / max(len(equity), 1)) - 1)
        if len(equity) > 0
        else 0.0,
        "annual_volatility": float(returns.std(ddof=0) * np.sqrt(252)) if not returns.empty else 0.0,
        "sharpe_ratio": sharpe_ratio(returns),
        "sortino_ratio": sortino_ratio(returns),
        "calmar_ratio": calmar_ratio(equity),
        "max_drawdown": max_drawdown(equity),
        **downside_metrics(returns),
    }


def summarise(
    equity: pd.Series,
    trades: pd.DataFrame | None = None,
    *,
    bootstrap: bool = False,
    n_bootstrap: int = 1000,
    bootstrap_alpha: float = 0.05,
    rng_seed: int | None = None,
) -> dict[str, Any]:
    returns = returns_from_equity(equity)
    summary = {
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "max_drawdown": max_drawdown(equity),
        "calmar": calmar_ratio(equity),
        "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1) if len(equity) > 0 else 0.0,
        "final_equity": float(equity.iloc[-1]) if len(equity) > 0 else 0.0,
        "n_bars": int(len(equity)),
        "volatility_ann": float(returns.std(ddof=0) * np.sqrt(252)),
    }
    if trades is not None:
        summary["n_trades"] = int(len(trades))
        summary["turnover"] = turnover(trades, equity)

    if bootstrap and len(returns) >= 30:
        try:
            cis = bootstrap_confidence_intervals(
                returns,
                equity=equity,
                n_bootstrap=int(n_bootstrap),
                alpha=float(bootstrap_alpha),
                rng_seed=rng_seed,
            )
            summary["confidence_intervals"] = cis
        except Exception:  # noqa: BLE001
            logger.debug("bootstrap CIs failed; omitting", exc_info=True)
    return summary


def bootstrap_confidence_intervals(
    returns: pd.Series,
    *,
    equity: pd.Series | None = None,
    n_bootstrap: int = 1000,
    alpha: float = 0.05,
    rng_seed: int | None = None,
) -> dict[str, dict[str, float]]:
    """Stationary bootstrap CIs for Sharpe / Sortino / MaxDD / Calmar.

    The function block-bootstraps the daily returns (default block
    length = sqrt(n)) to preserve auto-correlation, recomputes each
    statistic on each resample, and returns
    ``{statistic: {lower, upper, point}}`` at the ``[alpha/2, 1-alpha/2]``
    quantiles. The block length defends against IID-bootstrap bias on
    return series with serial correlation (the typical case for
    momentum / mean-reversion strategies).
    """
    if returns is None or len(returns) < 30:
        return {}
    rng = np.random.default_rng(rng_seed)
    arr = returns.to_numpy(dtype=float, copy=False)
    n = len(arr)
    block_len = max(2, int(np.sqrt(n)))
    n_blocks = int(np.ceil(n / block_len))

    sharpe_samples = np.empty(n_bootstrap, dtype=float)
    sortino_samples = np.empty(n_bootstrap, dtype=float)
    mdd_samples = np.empty(n_bootstrap, dtype=float)
    calmar_samples = np.empty(n_bootstrap, dtype=float)

    for i in range(n_bootstrap):
        starts = rng.integers(0, max(1, n - block_len + 1), size=n_blocks)
        sample = np.concatenate([arr[s : s + block_len] for s in starts])[:n]
        sample_series = pd.Series(sample)
        sharpe_samples[i] = sharpe_ratio(sample_series)
        sortino_samples[i] = sortino_ratio(sample_series)
        sample_equity = (1.0 + sample_series).cumprod()
        if not sample_equity.empty:
            mdd_samples[i] = max_drawdown(sample_equity)
            calmar_samples[i] = calmar_ratio(sample_equity)

    lower_q = float(alpha / 2.0)
    upper_q = float(1.0 - alpha / 2.0)

    def _ci(values: np.ndarray, point_value: float) -> dict[str, float]:
        return {
            "point": float(point_value),
            "lower": float(np.nanquantile(values, lower_q)),
            "upper": float(np.nanquantile(values, upper_q)),
        }

    point_sharpe = sharpe_ratio(returns)
    point_sortino = sortino_ratio(returns)
    point_mdd = max_drawdown(equity) if equity is not None else float(mdd_samples.mean())
    point_calmar = calmar_ratio(equity) if equity is not None else float(calmar_samples.mean())

    return {
        "sharpe": _ci(sharpe_samples, point_sharpe),
        "sortino": _ci(sortino_samples, point_sortino),
        "max_drawdown": _ci(mdd_samples, point_mdd),
        "calmar": _ci(calmar_samples, point_calmar),
        "n_bootstrap": {"point": float(n_bootstrap), "lower": float(n_bootstrap), "upper": float(n_bootstrap)},
    }


# ---------------------------------------------------------------------------
# Qlib-style analysis helpers (ports of ``qlib.contrib.evaluate``).
# ---------------------------------------------------------------------------


def risk_analysis(
    returns: pd.Series,
    freq: str = "day",
    mode: str = "sum",
    n_periods: int | None = None,
) -> dict[str, float]:
    """Qlib-style ``risk_analysis`` — summarise a return series.

    ``mode='sum'`` treats the returns as additive (pre-compounded); ``'product'``
    geometrically compounds them. ``n_periods`` overrides the annualisation
    factor (default inferred from ``freq``).
    """
    if returns is None or len(returns) == 0:
        return {
            "mean": 0.0,
            "std": 0.0,
            "annualized_return": 0.0,
            "information_ratio": 0.0,
            "max_drawdown": 0.0,
        }
    periods_per_year = {
        "day": 252,
        "daily": 252,
        "week": 52,
        "weekly": 52,
        "month": 12,
        "monthly": 12,
        "minute": 252 * 390,
    }.get(str(freq).lower(), 252)
    n = int(n_periods) if n_periods else periods_per_year

    clean = pd.Series(returns).dropna()
    if clean.empty:
        return {"mean": 0.0, "std": 0.0, "annualized_return": 0.0, "information_ratio": 0.0, "max_drawdown": 0.0}

    mean = float(clean.mean())
    std = float(clean.std(ddof=0))
    if mode == "product":
        annualized = float((1.0 + clean).prod() ** (n / max(len(clean), 1)) - 1.0)
        equity = (1 + clean).cumprod()
    else:
        annualized = float(mean * n)
        equity = clean.cumsum() + 1.0
    ir = float(np.sqrt(n) * mean / std) if std else 0.0
    mdd = float(((equity - equity.cummax()) / equity.cummax()).min()) if not equity.empty else 0.0
    return {
        "mean": mean,
        "std": std,
        "annualized_return": annualized,
        "information_ratio": ir,
        "max_drawdown": mdd,
    }


def turnover_report(trades: pd.DataFrame, equity: pd.Series) -> dict[str, float]:
    """Summarise a trades DataFrame with gross/net turnover + exposure.

    Expected columns: ``quantity`` (signed), ``price``. Missing columns
    degrade to a best-effort report rather than raising.
    """
    if trades is None or len(trades) == 0 or len(equity) == 0:
        return {"n_trades": 0, "turnover_gross": 0.0, "turnover_net": 0.0}
    qty = trades.get("quantity")
    price = trades.get("price")
    if qty is None or price is None:
        return {"n_trades": int(len(trades)), "turnover_gross": 0.0, "turnover_net": 0.0}
    notional_gross = float((qty.abs() * price).sum())
    notional_net = float((qty * price).sum())
    base = float(equity.iloc[0]) if len(equity) else 1.0
    return {
        "n_trades": int(len(trades)),
        "turnover_gross": notional_gross / max(base, 1e-9),
        "turnover_net": notional_net / max(base, 1e-9),
    }


def indicator_analysis(
    indicators: pd.DataFrame,
    columns: list[str] | None = None,
) -> dict[str, dict[str, float]]:
    """Summarise execution indicators (qlib ``indicator_analysis``).

    Given a frame with columns such as ``pa``, ``pos``, ``ffr``, compute
    mean / std / t-stat per column so the Strategy Test panel can display
    parity with qlib's port analysis record.
    """
    if indicators is None or indicators.empty:
        return {}
    cols = columns or [c for c in indicators.columns if c not in ("timestamp", "vt_symbol")]
    out: dict[str, dict[str, float]] = {}
    for c in cols:
        series = pd.to_numeric(indicators[c], errors="coerce").dropna()
        if series.empty:
            continue
        mean = float(series.mean())
        std = float(series.std(ddof=1) or np.nan)
        t = float(mean / (std / np.sqrt(len(series)))) if std else float("nan")
        out[c] = {
            "mean": mean,
            "std": std,
            "t_stat": t,
            "n": int(len(series)),
        }
    return out


# --- Plotly builders ------------------------------------------------------

def _fetch_equity_curve(backtest_id: str) -> pd.Series:
    from sqlalchemy import select

    from aqp.persistence.db import get_session
    from aqp.persistence.models import BacktestRun

    with get_session() as session:
        row = session.execute(
            select(BacktestRun).where(BacktestRun.id == backtest_id)
        ).scalar_one_or_none()
        if row is None or not row.metrics:
            return pd.Series(dtype=float)
        eq = row.metrics.get("equity_curve")
        if not eq:
            return pd.Series(dtype=float)
        idx = pd.to_datetime(list(eq.keys()))
        values = list(eq.values())
        return pd.Series(values, index=idx, name="equity")


def plot_equity_curve(backtest_id: str) -> go.Figure:
    eq = _fetch_equity_curve(backtest_id)
    fig = go.Figure()
    if not eq.empty:
        fig.add_trace(go.Scatter(x=eq.index, y=eq.values, mode="lines", name="Equity"))
    fig.update_layout(
        title=f"Equity Curve — {backtest_id[:8]}",
        xaxis_title="Date",
        yaxis_title="Equity",
        template="plotly_white",
    )
    return fig


def plot_drawdown(backtest_id: str) -> go.Figure:
    eq = _fetch_equity_curve(backtest_id)
    fig = go.Figure()
    if not eq.empty:
        dd = (eq - eq.cummax()) / eq.cummax()
        fig.add_trace(go.Scatter(x=dd.index, y=dd.values, fill="tozeroy", name="Drawdown"))
    fig.update_layout(
        title=f"Drawdown — {backtest_id[:8]}",
        xaxis_title="Date",
        yaxis_title="Drawdown",
        template="plotly_white",
    )
    return fig


def plot_returns_histogram(backtest_id: str) -> go.Figure:
    eq = _fetch_equity_curve(backtest_id)
    fig = go.Figure()
    if not eq.empty:
        rets = returns_from_equity(eq)
        fig.add_trace(go.Histogram(x=rets.values, nbinsx=50, name="Returns"))
    fig.update_layout(
        title=f"Return distribution — {backtest_id[:8]}",
        xaxis_title="Period return",
        yaxis_title="Frequency",
        template="plotly_white",
    )
    return fig
