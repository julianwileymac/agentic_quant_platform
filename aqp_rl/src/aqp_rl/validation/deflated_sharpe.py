"""Deflated Sharpe Ratio (DSR) — Bailey & López de Prado 2014.

Closed-form correction that deflates an empirical Sharpe ratio for
(a) multiple testing across ``N`` candidate strategies and (b) the
non-Gaussianity (skewness + kurtosis) of the returns distribution.

The output is a *probability* in ``[0, 1]`` representing the
likelihood that the strategy's true Sharpe is strictly positive
conditional on the observed empirical Sharpe and the diagnostic
search space.

All Sharpe ratios passed in must be **unannualised** (per-period).
Common bug: passing the annualised Sharpe (e.g. SR × sqrt(252))
yields nonsensical DSR values.

Reference: Bailey, D.H., & M. López de Prado (2014). "The Deflated
Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting,
and Non-Normality", *The Journal of Portfolio Management* 40 (5),
94-107.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import stats as sci_stats

_EULER_GAMMA = 0.5772156649015328606


def deflated_sharpe_ratio(
    returns: np.ndarray,
    *,
    sr_hat: float,
    sr_list: list[float] | np.ndarray,
    n_strategies_tested: int,
) -> float:
    """Compute the Deflated Sharpe Ratio (probability in ``[0, 1]``).

    Parameters
    ----------
    returns:
        ``(T,)`` array of per-period returns of the *winning* strategy.
        Used to estimate ``T``, skewness ``γ_3``, and excess kurtosis
        ``γ_4``.
    sr_hat:
        Empirical Sharpe ratio of the winning strategy
        (unannualised).
    sr_list:
        List of unannualised Sharpe ratios across the search space
        (used to estimate the variance ``V`` of the SR estimator
        across trials).
    n_strategies_tested:
        Total number of strategies tested ``N`` (≥ 1).

    Returns
    -------
    Probability ``∈ [0, 1]`` that the true Sharpe is > 0 after
    deflation. A value < 0.95 suggests the strategy may be
    overfitted.
    """
    r = np.asarray(returns, dtype=np.float64)
    r = r[~np.isnan(r)]
    T = len(r)
    if T < 3:
        raise ValueError(f"returns must have ≥ 3 observations; got T={T}")
    if n_strategies_tested < 1:
        raise ValueError(f"n_strategies_tested must be ≥ 1; got {n_strategies_tested!r}")
    g3 = float(sci_stats.skew(r))
    g4 = float(sci_stats.kurtosis(r, fisher=False))  # raw kurtosis (Gaussian = 3)
    sr_array = np.asarray(sr_list, dtype=np.float64)
    V = float(sr_array.var(ddof=1)) if sr_array.size > 1 else 0.0
    # SR_0 — expected maximum Sharpe under the null of zero true Sharpe
    # across N trials with variance V.
    sr0 = math.sqrt(V) * (
        (1 - _EULER_GAMMA) * sci_stats.norm.ppf(1 - 1 / n_strategies_tested)
        + _EULER_GAMMA
        * sci_stats.norm.ppf(
            1 - 1 / (n_strategies_tested * math.e)
        )
    )
    # SR estimator standard deviation (Bailey & López de Prado eq. 9).
    sigma_sr_sq = (1 - g3 * sr_hat + ((g4 - 1) / 4) * sr_hat ** 2) / (T - 1)
    if sigma_sr_sq <= 0:
        # Degenerate — the Bailey-López de Prado formula breaks down.
        # Fall back to the simpler Sharpe-distribution result (gaussian).
        sigma_sr = 1.0 / math.sqrt(max(T - 1, 1))
    else:
        sigma_sr = math.sqrt(sigma_sr_sq)
    z = (sr_hat - sr0) / max(sigma_sr, 1e-12)
    return float(sci_stats.norm.cdf(z))


__all__ = ["deflated_sharpe_ratio"]
