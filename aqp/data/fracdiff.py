"""Fractional differentiation (López de Prado, AFML ch. 5).

Integer differentiation (``diff()``) fully removes memory at the cost of
signal. Fractional differentiation parameterises the removal by ``d ∈
(0, 1)`` so a series can be made stationary while preserving as much
long-range memory as possible.

Two families:

* :func:`frac_diff_full` — expanding-window differentiation that uses all
  past weights (classical AFML formulation).
* :func:`frac_diff_ffd` — fixed-window ("FFD") where weights smaller than
  ``threshold`` are dropped. Recommended for practical use.

An helper :func:`find_min_d` runs an ADF test for a grid of ``d`` values
and returns the smallest value that makes the series stationary.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _get_weights(d: float, size: int) -> np.ndarray:
    """Binomial weights ``w_k = (-1)^k * C(d, k)`` up to ``size`` lags."""
    w = [1.0]
    for k in range(1, int(size)):
        w_ = -w[-1] / k * (d - k + 1)
        w.append(w_)
    return np.array(w[::-1])


def frac_diff_full(series: pd.Series | pd.DataFrame, d: float) -> pd.DataFrame:
    """Fractionally-differenced expanding-window series."""
    if isinstance(series, pd.Series):
        frame = series.to_frame()
    else:
        frame = series
    out = pd.DataFrame(index=frame.index, columns=frame.columns, dtype=float)
    for col in frame.columns:
        col_series = frame[col].ffill().dropna()
        w = _get_weights(d, len(col_series))
        tau = int(len(w) * 1e-2)
        values = np.full(len(col_series), np.nan, dtype=float)
        for i in range(tau, len(col_series)):
            values[i] = float(np.dot(w[-(i + 1) :], col_series.iloc[: i + 1].values))
        out[col] = pd.Series(values, index=col_series.index)
    return out


def _get_weights_ffd(d: float, threshold: float) -> np.ndarray:
    """Weights clipped once their magnitude falls below ``threshold``."""
    w = [1.0]
    k = 1
    while True:
        w_ = -w[-1] / k * (d - k + 1)
        if abs(w_) < threshold:
            break
        w.append(w_)
        k += 1
    return np.array(w[::-1])


def frac_diff_ffd(
    series: pd.Series | pd.DataFrame,
    d: float,
    threshold: float = 1e-4,
) -> pd.DataFrame:
    """Fixed-window fractional differentiation."""
    if isinstance(series, pd.Series):
        frame = series.to_frame()
    else:
        frame = series
    w = _get_weights_ffd(d, threshold)
    window = len(w)
    out = pd.DataFrame(index=frame.index, columns=frame.columns, dtype=float)
    for col in frame.columns:
        col_series = frame[col].ffill().dropna()
        values = np.full(len(col_series), np.nan, dtype=float)
        for i in range(window - 1, len(col_series)):
            values[i] = float(np.dot(w, col_series.iloc[i - window + 1 : i + 1].values))
        out[col] = pd.Series(values, index=col_series.index)
    return out


def find_min_d(
    series: pd.Series,
    d_grid: tuple[float, ...] = tuple(i * 0.1 for i in range(11)),
    threshold: float = 1e-4,
    p_critical: float = 0.05,
) -> float:
    """Return the smallest ``d`` that makes the series stationary (ADF)."""
    try:
        from statsmodels.tsa.stattools import adfuller
    except Exception:
        logger.warning("statsmodels missing; find_min_d returning 1.0 (full diff).")
        return 1.0
    for d in d_grid:
        ffd = frac_diff_ffd(series, d=d, threshold=threshold).dropna().iloc[:, 0]
        if len(ffd) < 20:
            continue
        p = adfuller(ffd, maxlag=1, regression="c", autolag=None)[1]
        if p < p_critical:
            return float(d)
    return 1.0


__all__ = [
    "find_min_d",
    "frac_diff_ffd",
    "frac_diff_full",
]
