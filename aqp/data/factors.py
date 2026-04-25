"""Alphalens-style factor evaluation (from the ML4T book).

Given a **factor frame** ``(timestamp, vt_symbol) -> factor_value`` and a
**prices frame** ``(timestamp, vt_symbol) -> price``, produce:

- `FactorReport.forward_returns` — panel of forward returns per horizon.
- `FactorReport.ic` — daily Information Coefficient per horizon.
- `FactorReport.ic_summary` — IC mean, std, t-stat, IR, hit-rate.
- `FactorReport.quantile_returns` — cumulative returns per factor quantile.
- `FactorReport.quantile_spreads` — top-minus-bottom spread per date.
- `FactorReport.turnover` — fraction of the top quantile that changes per date.

Also ships Plotly figure builders so the Factor Evaluation UI page can
render tear sheets without any extra dependencies.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core transformations
# ---------------------------------------------------------------------------


def compute_forward_returns(
    prices: pd.DataFrame,
    periods: tuple[int, ...] = (1, 5, 10, 21),
    price_column: str = "close",
) -> pd.DataFrame:
    """Return a long-format frame of forward returns per ``(timestamp, symbol)``.

    Expected ``prices`` layout: columns ``timestamp``, ``vt_symbol``,
    ``price_column``. Output adds ``fwd_{k}`` columns for each period.
    """
    if prices.empty:
        return pd.DataFrame()
    df = prices.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["vt_symbol", "timestamp"]).reset_index(drop=True)
    for period in periods:
        df[f"fwd_{period}"] = (
            df.groupby("vt_symbol")[price_column].shift(-period) / df[price_column] - 1
        )
    keep = ["timestamp", "vt_symbol", price_column, *[f"fwd_{p}" for p in periods]]
    return df[keep]


def align_factor_and_returns(
    factor: pd.DataFrame,
    forward_returns: pd.DataFrame,
    factor_column: str = "factor",
) -> pd.DataFrame:
    """Inner-join the factor and the forward-returns panel on ``(timestamp, vt_symbol)``."""
    if factor.empty or forward_returns.empty:
        return pd.DataFrame()
    left = factor.copy()
    left["timestamp"] = pd.to_datetime(left["timestamp"])
    merged = forward_returns.merge(
        left[["timestamp", "vt_symbol", factor_column]],
        on=["timestamp", "vt_symbol"],
        how="inner",
    )
    merged = merged.rename(columns={factor_column: "factor"})
    return merged


def factor_information_coefficient(
    aligned: pd.DataFrame,
    method: str = "spearman",
) -> pd.DataFrame:
    """Daily IC (Spearman by default) per forward-return horizon."""
    if aligned.empty:
        return pd.DataFrame()
    horizons = [c for c in aligned.columns if c.startswith("fwd_")]
    rows = []
    for timestamp, group in aligned.groupby("timestamp"):
        row: dict[str, Any] = {"timestamp": timestamp}
        for h in horizons:
            sub = group[["factor", h]].dropna()
            if len(sub) < 3:
                row[h] = np.nan
                continue
            row[h] = sub["factor"].corr(sub[h], method=method)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


def ic_summary(ic_ts: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Scalar summary — mean IC, IR (mean/std), hit-rate, t-stat per horizon."""
    out: dict[str, dict[str, float]] = {}
    for col in ic_ts.columns:
        if col == "timestamp":
            continue
        series = ic_ts[col].dropna()
        if series.empty:
            continue
        mean = float(series.mean())
        std = float(series.std(ddof=1) or np.nan)
        ir = float(mean / std) if std and not np.isnan(std) else float("nan")
        t_stat = float(mean / (std / np.sqrt(len(series)))) if std else float("nan")
        hit_rate = float((series > 0).mean())
        out[col] = {
            "mean": mean,
            "std": std,
            "ir": ir,
            "t_stat": t_stat,
            "hit_rate": hit_rate,
            "observations": int(len(series)),
        }
    return out


def _assign_quantiles(group: pd.DataFrame, n_quantiles: int) -> pd.Series:
    if group["factor"].nunique() < n_quantiles:
        # Fallback: rank into equal-size groups by argsort.
        ranks = group["factor"].rank(method="first")
        return pd.cut(ranks, bins=n_quantiles, labels=False) + 1
    try:
        return pd.qcut(group["factor"], n_quantiles, labels=False, duplicates="drop") + 1
    except ValueError:
        ranks = group["factor"].rank(method="first")
        return pd.cut(ranks, bins=n_quantiles, labels=False) + 1


def mean_returns_by_quantile(
    aligned: pd.DataFrame,
    n_quantiles: int = 5,
    horizon_column: str = "fwd_1",
) -> pd.DataFrame:
    """Cross-sectional mean forward return per quantile per date."""
    if aligned.empty:
        return pd.DataFrame()
    df = aligned.copy()
    df["quantile"] = df.groupby("timestamp").apply(
        lambda g: _assign_quantiles(g, n_quantiles), include_groups=False
    ).reset_index(level=0, drop=True)
    df = df.dropna(subset=["quantile"])
    df["quantile"] = df["quantile"].astype(int)
    grouped = df.groupby(["timestamp", "quantile"])[horizon_column].mean().reset_index()
    pivot = grouped.pivot(index="timestamp", columns="quantile", values=horizon_column)
    pivot.columns = [f"Q{int(c)}" for c in pivot.columns]
    pivot = pivot.sort_index()
    return pivot


def quantile_spread(quantile_returns: pd.DataFrame) -> pd.Series:
    """Top-minus-bottom spread of the quantile-returns panel."""
    if quantile_returns.empty:
        return pd.Series(dtype=float)
    cols = sorted(quantile_returns.columns, key=lambda c: int(c.lstrip("Q")))
    return quantile_returns[cols[-1]] - quantile_returns[cols[0]]


def cumulative_quantile_returns(quantile_returns: pd.DataFrame) -> pd.DataFrame:
    """Cumulative geometric returns for each quantile over time."""
    if quantile_returns.empty:
        return quantile_returns
    return (1 + quantile_returns.fillna(0)).cumprod() - 1


def turnover_top_quantile(
    aligned: pd.DataFrame,
    n_quantiles: int = 5,
) -> pd.Series:
    """Per-date fraction of the top quantile that rotated out vs. yesterday."""
    if aligned.empty:
        return pd.Series(dtype=float)
    df = aligned.copy()
    df["quantile"] = df.groupby("timestamp").apply(
        lambda g: _assign_quantiles(g, n_quantiles), include_groups=False
    ).reset_index(level=0, drop=True)
    df = df.dropna(subset=["quantile"])
    df["quantile"] = df["quantile"].astype(int)
    top = df[df["quantile"] == n_quantiles]
    by_date = top.groupby("timestamp")["vt_symbol"].agg(set)
    dates = by_date.index.tolist()
    values: list[float] = []
    for i in range(1, len(dates)):
        prev_set = by_date.iloc[i - 1]
        cur_set = by_date.iloc[i]
        if not prev_set:
            values.append(0.0)
            continue
        values.append(len(prev_set - cur_set) / len(prev_set))
    return pd.Series(values, index=dates[1:])


# ---------------------------------------------------------------------------
# Report dataclass + top-level helper
# ---------------------------------------------------------------------------


@dataclass
class FactorReport:
    """Bundle of every statistic produced by :func:`evaluate_factor`."""

    factor_name: str
    periods: tuple[int, ...]
    forward_returns: pd.DataFrame = field(default_factory=pd.DataFrame)
    aligned: pd.DataFrame = field(default_factory=pd.DataFrame)
    ic: pd.DataFrame = field(default_factory=pd.DataFrame)
    ic_stats: dict[str, dict[str, float]] = field(default_factory=dict)
    quantile_returns: pd.DataFrame = field(default_factory=pd.DataFrame)
    cumulative_returns: pd.DataFrame = field(default_factory=pd.DataFrame)
    quantile_spread: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    turnover: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor_name": self.factor_name,
            "periods": list(self.periods),
            "ic_stats": self.ic_stats,
            "ic_series": self.ic.to_dict(orient="list") if not self.ic.empty else {},
            "cumulative_returns": self.cumulative_returns.to_dict() if not self.cumulative_returns.empty else {},
            "quantile_spread": (
                {str(k): float(v) for k, v in self.quantile_spread.tail(250).to_dict().items()}
                if not self.quantile_spread.empty
                else {}
            ),
            "turnover_mean": float(self.turnover.mean()) if not self.turnover.empty else 0.0,
        }


def evaluate_factor(
    factor: pd.DataFrame,
    prices: pd.DataFrame,
    factor_name: str = "factor",
    factor_column: str = "factor",
    periods: tuple[int, ...] = (1, 5, 10, 21),
    n_quantiles: int = 5,
    price_column: str = "close",
) -> FactorReport:
    """End-to-end factor evaluation.

    Arguments:
    - ``factor``: long-format ``(timestamp, vt_symbol, factor_column)``.
    - ``prices``: long-format ``(timestamp, vt_symbol, price_column)``.
    """
    fwd = compute_forward_returns(prices, periods=periods, price_column=price_column)
    aligned = align_factor_and_returns(factor, fwd, factor_column=factor_column)
    ic = factor_information_coefficient(aligned)
    q_ret = mean_returns_by_quantile(aligned, n_quantiles=n_quantiles, horizon_column=f"fwd_{periods[0]}")
    cum = cumulative_quantile_returns(q_ret)
    spread = quantile_spread(q_ret)
    turnover = turnover_top_quantile(aligned, n_quantiles=n_quantiles)
    return FactorReport(
        factor_name=factor_name,
        periods=periods,
        forward_returns=fwd,
        aligned=aligned,
        ic=ic,
        ic_stats=ic_summary(ic),
        quantile_returns=q_ret,
        cumulative_returns=cum,
        quantile_spread=spread,
        turnover=turnover,
    )


# ---------------------------------------------------------------------------
# Plot builders (Plotly)
# ---------------------------------------------------------------------------


def plot_ic_decay(ic: pd.DataFrame) -> Any:
    """Bar chart of mean IC per forward-return horizon."""
    import plotly.graph_objects as go

    if ic.empty:
        return go.Figure(layout={"title": "IC Decay (no data)"})
    means = {c: float(ic[c].mean()) for c in ic.columns if c != "timestamp"}
    fig = go.Figure([go.Bar(x=list(means.keys()), y=list(means.values()))])
    fig.update_layout(title="Mean IC by Horizon", xaxis_title="horizon", yaxis_title="IC")
    return fig


def plot_quantile_returns(cumulative_returns: pd.DataFrame) -> Any:
    """Line chart of cumulative quantile returns."""
    import plotly.graph_objects as go

    if cumulative_returns.empty:
        return go.Figure(layout={"title": "Cumulative returns by quantile (no data)"})
    fig = go.Figure()
    for col in cumulative_returns.columns:
        fig.add_trace(
            go.Scatter(
                x=cumulative_returns.index,
                y=cumulative_returns[col],
                mode="lines",
                name=str(col),
            )
        )
    fig.update_layout(title="Cumulative Returns by Quantile", xaxis_title="date", yaxis_title="cumret")
    return fig


def plot_turnover(turnover: pd.Series) -> Any:
    """Line chart of top-quantile turnover over time."""
    import plotly.graph_objects as go

    if turnover.empty:
        return go.Figure(layout={"title": "Turnover (no data)"})
    fig = go.Figure(
        [go.Scatter(x=turnover.index, y=turnover.values, mode="lines", name="top-Q turnover")]
    )
    fig.update_layout(title="Top-Quantile Turnover", xaxis_title="date", yaxis_title="fraction")
    return fig
