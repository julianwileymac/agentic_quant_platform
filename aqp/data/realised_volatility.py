"""OHLC realised volatility estimators.

Implements close-to-close, Parkinson, Garman-Klass, Rogers-Satchell, and
Yang-Zhang estimators on rolling windows of OHLC bars. Returns annualised
volatility (sigma) in the same units as input returns (i.e. unitless).

Source: ``inspiration/notebooks-master/realised_volatility.ipynb``
(Santander 2012 + the broader OHLC-vol literature).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _check(open_: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series) -> None:
    n = len(open_)
    if not all(len(s) == n for s in (high, low, close)):
        raise ValueError("OHLC series must be the same length")


def close_to_close(close: pd.Series, period: int = 20, annualize: int | None = 252) -> pd.Series:
    """Standard log-return based volatility on close-to-close returns."""
    log_ret = np.log(close / close.shift(1))
    sigma = log_ret.rolling(period).std()
    if annualize:
        sigma = sigma * np.sqrt(annualize)
    return sigma


def parkinson(high: pd.Series, low: pd.Series, period: int = 20, annualize: int | None = 252) -> pd.Series:
    """Parkinson 1980 volatility — uses high/low range only.

    sigma^2_P = (1 / (4 * ln 2)) * mean(log(H/L)^2)
    """
    log_hl_sq = np.log(high / low) ** 2
    var = log_hl_sq.rolling(period).mean() / (4.0 * np.log(2.0))
    sigma = np.sqrt(var)
    if annualize:
        sigma = sigma * np.sqrt(annualize)
    return sigma


def garman_klass(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
    annualize: int | None = 252,
) -> pd.Series:
    """Garman-Klass 1980 OHLC volatility.

    sigma^2_GK = mean(0.5 * (log(H/L))^2 - (2 ln 2 - 1) * (log(C/O))^2)
    """
    _check(open_, high, low, close)
    term1 = 0.5 * (np.log(high / low) ** 2)
    term2 = (2.0 * np.log(2.0) - 1.0) * (np.log(close / open_) ** 2)
    var = (term1 - term2).rolling(period).mean()
    sigma = np.sqrt(var.clip(lower=0))
    if annualize:
        sigma = sigma * np.sqrt(annualize)
    return sigma


def rogers_satchell(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
    annualize: int | None = 252,
) -> pd.Series:
    """Rogers-Satchell 1991 — drift-independent OHLC volatility.

    sigma^2_RS = mean(log(H/C)*log(H/O) + log(L/C)*log(L/O))
    """
    _check(open_, high, low, close)
    term = np.log(high / close) * np.log(high / open_) + np.log(low / close) * np.log(low / open_)
    var = term.rolling(period).mean()
    sigma = np.sqrt(var.clip(lower=0))
    if annualize:
        sigma = sigma * np.sqrt(annualize)
    return sigma


def yang_zhang(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
    annualize: int | None = 252,
    k: float | None = None,
) -> pd.Series:
    """Yang-Zhang 2000 — combines overnight + open-to-close + Rogers-Satchell.

    sigma^2_YZ = sigma^2_O + k * sigma^2_C + (1 - k) * sigma^2_RS
    where k ~= 0.34 / (1.34 + (n+1)/(n-1)) by default.
    """
    _check(open_, high, low, close)
    n = period
    if k is None:
        k = 0.34 / (1.34 + (n + 1.0) / (n - 1.0))

    overnight = np.log(open_ / close.shift(1))
    sigma_o2 = overnight.rolling(period).var()

    intraday = np.log(close / open_)
    sigma_c2 = intraday.rolling(period).var()

    rs2 = (
        np.log(high / close) * np.log(high / open_)
        + np.log(low / close) * np.log(low / open_)
    )
    sigma_rs2 = rs2.rolling(period).mean()

    var = sigma_o2 + k * sigma_c2 + (1.0 - k) * sigma_rs2
    sigma = np.sqrt(var.clip(lower=0))
    if annualize:
        sigma = sigma * np.sqrt(annualize)
    return sigma


_ESTIMATORS = {
    "close_to_close": close_to_close,
    "parkinson": parkinson,
    "garman_klass": garman_klass,
    "rogers_satchell": rogers_satchell,
    "yang_zhang": yang_zhang,
}


def compare_estimators(
    bars: pd.DataFrame,
    period: int = 20,
    annualize: int | None = 252,
) -> pd.DataFrame:
    """Compute all five estimators on the same OHLC frame.

    ``bars`` must have columns ``open, high, low, close``.
    Returns a DataFrame with one column per estimator.
    """
    open_, high, low, close = bars["open"], bars["high"], bars["low"], bars["close"]
    return pd.DataFrame(
        {
            "close_to_close": close_to_close(close, period, annualize),
            "parkinson": parkinson(high, low, period, annualize),
            "garman_klass": garman_klass(open_, high, low, close, period, annualize),
            "rogers_satchell": rogers_satchell(open_, high, low, close, period, annualize),
            "yang_zhang": yang_zhang(open_, high, low, close, period, annualize),
        }
    )


__all__ = [
    "close_to_close",
    "compare_estimators",
    "garman_klass",
    "parkinson",
    "rogers_satchell",
    "yang_zhang",
]
