"""Cointegration utilities for stat-arb / pairs / spread research.

Source: ``inspiration/notebooks-master/commodity_crack_spread_stat_arb.ipynb``
and the Engle-Granger / Johansen literature.

We wrap :mod:`statsmodels` so the import is hard. Callers needing to run
on environments without statsmodels can use the small fallback ADF
function (``_adf_fallback``); production callers should rely on
statsmodels.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ADFResult:
    statistic: float
    p_value: float
    used_lag: int
    n_obs: int
    critical_values: dict[str, float]
    is_stationary_5pct: bool


@dataclass
class EngleGrangerResult:
    cointegrated: bool
    p_value: float
    hedge_ratio: float
    intercept: float
    spread: pd.Series
    spread_z: pd.Series
    half_life: float


def adf_test(series: pd.Series, max_lag: int | None = None, regression: str = "c") -> ADFResult:
    """Augmented Dickey-Fuller stationarity test.

    Returns :class:`ADFResult` with the test statistic and p-value plus a
    convenience ``is_stationary_5pct`` flag.
    """
    try:
        from statsmodels.tsa.stattools import adfuller
    except ImportError as exc:  # pragma: no cover - hard fail in prod
        raise ImportError("statsmodels is required for adf_test; pip install statsmodels") from exc

    clean = series.dropna()
    if len(clean) < 10:
        raise ValueError(f"Need at least 10 observations for ADF, got {len(clean)}")
    result = adfuller(clean, maxlag=max_lag, regression=regression, autolag="AIC")
    return ADFResult(
        statistic=float(result[0]),
        p_value=float(result[1]),
        used_lag=int(result[2]),
        n_obs=int(result[3]),
        critical_values={k: float(v) for k, v in result[4].items()},
        is_stationary_5pct=bool(result[1] < 0.05),
    )


def _ols_hedge_ratio(y: pd.Series, x: pd.Series) -> tuple[float, float, pd.Series]:
    """OLS regression ``y = alpha + beta * x``; returns ``(beta, alpha, residual)``."""
    df = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    n = len(df)
    if n < 2:
        raise ValueError(f"Need at least 2 observations, got {n}")
    x_arr = df["x"].to_numpy()
    y_arr = df["y"].to_numpy()
    x_mean, y_mean = x_arr.mean(), y_arr.mean()
    cov = ((x_arr - x_mean) * (y_arr - y_mean)).sum()
    var = ((x_arr - x_mean) ** 2).sum()
    beta = cov / var if var > 1e-12 else 0.0
    alpha = y_mean - beta * x_mean
    spread = y - (alpha + beta * x)
    return float(beta), float(alpha), spread


def _half_life(spread: pd.Series) -> float:
    """OU half-life via lag-1 autoregression on differences.

    half-life = -ln(2) / ln(1 - lambda) where lambda is the AR(1) coefficient
    on the differenced series.
    """
    s = spread.dropna()
    if len(s) < 5:
        return float("nan")
    s_lag = s.shift(1).dropna()
    s_diff = s.diff().dropna()
    common = s_lag.index.intersection(s_diff.index)
    if len(common) < 3:
        return float("nan")
    x = s_lag.loc[common].to_numpy()
    y = s_diff.loc[common].to_numpy()
    var = ((x - x.mean()) ** 2).sum()
    if var < 1e-12:
        return float("nan")
    lam = ((x - x.mean()) * (y - y.mean())).sum() / var
    if lam >= 0 or lam <= -1:
        return float("nan")
    return float(-np.log(2.0) / np.log(1.0 + lam))


def engle_granger(
    y: pd.Series,
    x: pd.Series,
    z_window: int = 60,
    significance: float = 0.05,
) -> EngleGrangerResult:
    """Engle-Granger 2-step cointegration test.

    1. OLS hedge ratio from y on x.
    2. ADF test on the residual.
    Returns a cointegration decision plus the spread, its rolling z-score,
    and the OU half-life of mean reversion.
    """
    try:
        from statsmodels.tsa.stattools import coint
    except ImportError as exc:  # pragma: no cover
        raise ImportError("statsmodels is required for engle_granger; pip install statsmodels") from exc

    df = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    if len(df) < 10:
        raise ValueError(f"Need at least 10 paired observations, got {len(df)}")
    score, p_value, _ = coint(df["y"], df["x"])
    beta, alpha, spread = _ols_hedge_ratio(df["y"], df["x"])
    spread_full = y - (alpha + beta * x)
    rolling = spread_full.rolling(z_window, min_periods=z_window // 2)
    spread_z = (spread_full - rolling.mean()) / rolling.std().replace(0.0, np.nan)
    return EngleGrangerResult(
        cointegrated=bool(p_value < significance),
        p_value=float(p_value),
        hedge_ratio=float(beta),
        intercept=float(alpha),
        spread=spread_full,
        spread_z=spread_z,
        half_life=_half_life(spread_full),
    )


def kalman_hedge_ratio(
    y: pd.Series,
    x: pd.Series,
    delta: float = 1e-4,
    obs_var: float = 1e-3,
) -> pd.Series:
    """Kalman-filter time-varying hedge ratio between ``y`` and ``x``.

    Implementation follows Chan 2013 — minimal pure-numpy Kalman update
    with a 2-state (intercept, beta) regression model. Returns the
    smoothed beta time series aligned to ``y.index``.
    """
    df = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    n = len(df)
    if n < 2:
        raise ValueError(f"Need at least 2 paired observations, got {n}")

    state = np.zeros(2)  # [intercept, beta]
    cov = np.eye(2)
    proc_var = delta / (1.0 - delta) * np.eye(2)

    betas = np.zeros(n)
    for i, (y_i, x_i) in enumerate(zip(df["y"].to_numpy(), df["x"].to_numpy(), strict=False)):
        # predict
        cov = cov + proc_var
        # observation
        h = np.array([1.0, x_i])
        innovation = y_i - h @ state
        s = h @ cov @ h.T + obs_var
        k_gain = cov @ h.T / s
        state = state + k_gain * innovation
        cov = cov - np.outer(k_gain, h) @ cov
        betas[i] = state[1]

    return pd.Series(betas, index=df.index, name="kalman_beta").reindex(y.index)


def find_cointegrated_pairs(
    panel: pd.DataFrame,
    significance: float = 0.05,
    z_window: int = 60,
) -> list[dict[str, Any]]:
    """Brute-force search for cointegrated pairs in a price panel.

    ``panel`` is a wide DataFrame indexed by timestamp with one column per
    symbol. Returns sorted list of dicts (ascending p-value).
    """
    cols = list(panel.columns)
    pairs: list[dict[str, Any]] = []
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            try:
                r = engle_granger(panel[a], panel[b], z_window=z_window, significance=significance)
            except (ValueError, ImportError):
                continue
            if r.cointegrated:
                pairs.append(
                    {
                        "asset_a": a,
                        "asset_b": b,
                        "p_value": r.p_value,
                        "hedge_ratio": r.hedge_ratio,
                        "half_life": r.half_life,
                    }
                )
    return sorted(pairs, key=lambda d: d["p_value"])


__all__ = [
    "ADFResult",
    "EngleGrangerResult",
    "adf_test",
    "engle_granger",
    "find_cointegrated_pairs",
    "kalman_hedge_ratio",
]
