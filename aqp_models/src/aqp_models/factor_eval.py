"""Alphalens-style factor evaluation.

A compact, zero-dep factor tearsheet builder:

- :func:`compute_ic` — Information Coefficient per horizon.
- :func:`compute_rank_ic` — Spearman rank IC per horizon.
- :func:`quantile_returns` — bucketed forward returns across ``n_quantiles``.
- :func:`turnover` — time-series of factor-rank turnover.
- :func:`factor_tearsheet` — HTML rollup of the above (matplotlib +
  inline PNGs, no Jupyter-ext-only dependencies).

Result dicts are MLflow-friendly so
:func:`aqp.mlops.mlflow_client.log_factor_run` can log them directly.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Iterable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _forward_returns(close_panel: pd.DataFrame, horizons: Iterable[int]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for h in horizons:
        ret = close_panel.pct_change(h).shift(-h)
        stacked = ret.stack().rename(f"ret_{h}d")
        frames.append(stacked)
    return pd.concat(frames, axis=1)


def compute_ic(
    factor: pd.Series,
    close_panel: pd.DataFrame,
    horizons: Iterable[int] = (1, 5, 10, 21),
) -> pd.DataFrame:
    """Pearson IC per horizon (``factor × forward_return``)."""
    fwd = _forward_returns(close_panel, horizons)
    aligned = factor.to_frame("factor").join(fwd, how="inner")
    records: list[dict[str, float]] = []
    for col in fwd.columns:
        ic = aligned.groupby(level=0).apply(
            lambda df, c=col: df["factor"].corr(df[c])
        )
        records.append(
            {
                "horizon": col,
                "ic_mean": float(ic.mean() or 0.0),
                "ic_std": float(ic.std() or 0.0),
                "ic_ir": float((ic.mean() / ic.std()) if (ic.std() and ic.std() != 0) else 0.0),
                "n_obs": int(ic.count()),
            }
        )
    return pd.DataFrame(records).set_index("horizon")


def compute_rank_ic(
    factor: pd.Series,
    close_panel: pd.DataFrame,
    horizons: Iterable[int] = (1, 5, 10, 21),
) -> pd.DataFrame:
    """Spearman rank IC per horizon."""
    fwd = _forward_returns(close_panel, horizons)
    aligned = factor.to_frame("factor").join(fwd, how="inner")
    records: list[dict[str, float]] = []
    for col in fwd.columns:
        ic = aligned.groupby(level=0).apply(
            lambda df, c=col: df["factor"].corr(df[c], method="spearman")
        )
        records.append(
            {
                "horizon": col,
                "rank_ic_mean": float(ic.mean() or 0.0),
                "rank_ic_std": float(ic.std() or 0.0),
                "rank_ic_ir": float((ic.mean() / ic.std()) if (ic.std() and ic.std() != 0) else 0.0),
                "n_obs": int(ic.count()),
            }
        )
    return pd.DataFrame(records).set_index("horizon")


def quantile_returns(
    factor: pd.Series,
    close_panel: pd.DataFrame,
    horizons: Iterable[int] = (5, 21),
    n_quantiles: int = 5,
) -> pd.DataFrame:
    """Mean forward-return per factor quantile per horizon."""
    fwd = _forward_returns(close_panel, horizons)
    aligned = factor.to_frame("factor").join(fwd, how="inner")

    def _bucket(sub: pd.DataFrame) -> pd.Series:
        try:
            q = pd.qcut(sub["factor"].rank(method="first"), n_quantiles, labels=False) + 1
        except Exception:
            q = pd.Series(np.nan, index=sub.index)
        return q

    aligned["q"] = aligned.groupby(level=0, group_keys=False).apply(_bucket)
    rows: list[dict[str, float]] = []
    for h_col in fwd.columns:
        by_q = aligned.dropna(subset=["q"]).groupby("q")[h_col].mean()
        for q, val in by_q.items():
            rows.append({"horizon": h_col, "quantile": int(q), "mean_fwd_return": float(val)})
    return pd.DataFrame(rows).set_index(["horizon", "quantile"])


def turnover(factor: pd.Series, window: int = 1) -> pd.Series:
    if not isinstance(factor.index, pd.MultiIndex):
        raise ValueError("factor must be a MultiIndex (timestamp, vt_symbol) series")
    ranks = factor.groupby(level=0).rank()
    lagged = ranks.groupby(level=1).shift(window)
    diff = (ranks - lagged).abs()
    return diff.groupby(level=0).mean().rename("turnover")


def factor_tearsheet(
    factor_name: str,
    factor: pd.Series,
    close_panel: pd.DataFrame,
    horizons: Iterable[int] = (1, 5, 10, 21),
    n_quantiles: int = 5,
) -> dict[str, object]:
    """Return a dict with IC/rank-IC/quantile tables + a base64 PNG chart."""
    ic = compute_ic(factor, close_panel, horizons=horizons)
    rank_ic = compute_rank_ic(factor, close_panel, horizons=horizons)
    qr = quantile_returns(factor, close_panel, horizons=horizons, n_quantiles=n_quantiles)
    to = turnover(factor)

    chart_png: str | None = None
    try:  # pragma: no cover - optional dep
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        ic["ic_mean"].plot.bar(ax=axes[0], title=f"{factor_name} IC (mean)")
        qr.reset_index().pivot(index="quantile", columns="horizon", values="mean_fwd_return").plot.bar(
            ax=axes[1], title=f"{factor_name} mean fwd return by quantile"
        )
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        chart_png = base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        logger.debug("matplotlib not available; chart omitted", exc_info=True)

    return {
        "factor": factor_name,
        "ic": ic,
        "rank_ic": rank_ic,
        "quantile_returns": qr,
        "turnover_mean": float(to.mean() or 0.0),
        "chart_png_b64": chart_png,
    }


__all__ = [
    "compute_ic",
    "compute_rank_ic",
    "factor_tearsheet",
    "quantile_returns",
    "turnover",
]
