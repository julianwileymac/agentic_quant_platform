"""Deflated Sharpe Ratio (Bailey & López de Prado, 2014).

The plan §13 risk register: "Deflated Sharpe Ratio requires honest
tracking of all trial counts. If users can reuse a graph across many
sweeps without the platform logging the full trial count, DSR is
fiction. The :class:`LabRun` ledger must include
``total_trials_searched`` so DSR is computable post-hoc."

The Lab schema mandates ``LabRun.total_trials_searched`` (Alembic
0057, default 1). The Evaluation compiler sets it to the size of the
sweep grid, the runtime persists it, and the UI surface here renders
the DSR alongside the raw Sharpe (NEVER raw Sharpe alone, per the
Phase 3 contract).

References:

- Bailey, D. & López de Prado, M. (2014). "The Deflated Sharpe Ratio:
  Correcting for Selection Bias, Backtest Overfitting and Non-
  Normality." Journal of Portfolio Management, 40(5), 94-107.
"""
from __future__ import annotations

import math


# ``EULER_GAMMA`` is the Euler-Mascheroni constant (used in the
# expected-maximum-of-N-trials approximation).
_EULER_GAMMA = 0.5772156649015329


def _phi(x: float) -> float:
    """Standard-normal CDF (cheap erf-based approximation)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def probabilistic_sharpe_ratio(
    observed_sharpe: float,
    *,
    n_obs: int,
    benchmark_sharpe: float = 0.0,
    skewness: float = 0.0,
    excess_kurtosis: float = 0.0,
) -> float:
    """Probabilistic Sharpe Ratio (PSR).

    PSR is the probability that the observed Sharpe exceeds the
    benchmark Sharpe, accounting for skew + kurtosis (which inflate
    variance and reduce confidence).
    """
    if n_obs <= 1:
        return 0.0
    numerator = (observed_sharpe - benchmark_sharpe) * math.sqrt(n_obs - 1)
    # Bailey & López de Prado (2014) — the denominator uses the FULL
    # kurtosis (not excess). When excess_kurtosis=0 the series is
    # mesokurtic so kurtosis=3 and the bracket reduces to (3-1)/4 = 0.5.
    kurtosis = excess_kurtosis + 3.0
    denom_sq = (
        1.0
        - skewness * observed_sharpe
        + ((kurtosis - 1.0) / 4.0) * observed_sharpe**2
    )
    if denom_sq <= 0:
        return 0.0
    return _phi(numerator / math.sqrt(denom_sq))


def deflated_sharpe_ratio(
    observed_sharpe: float,
    *,
    n_obs: int,
    n_trials: int,
    variance_of_sharpes: float | None = None,
    skewness: float = 0.0,
    excess_kurtosis: float = 0.0,
) -> float:
    """Deflated Sharpe Ratio (DSR).

    DSR = PSR(SR_observed | SR_benchmark = expected_max_of_N_trials).
    The expected-maximum approximation uses the Euler-Mascheroni
    constant per Bailey & López de Prado (2014, eq. 8).

    Parameters
    ----------
    observed_sharpe:
        The Sharpe ratio of the candidate strategy.
    n_obs:
        Number of return observations.
    n_trials:
        Total number of strategies / parameter combinations TRIED
        (NOT just selected). Read off ``LabRun.total_trials_searched``
        per the plan's §16 honest-tracking contract.
    variance_of_sharpes:
        Variance of the Sharpe ratios across all trials. When None we
        fall back to the conservative ``1 / (n_obs - 1)`` approximation
        (Bailey & López de Prado 2014, eq. 9 lower bound).
    skewness, excess_kurtosis:
        Higher-moment corrections from the candidate's return series.
    """
    if n_trials <= 1:
        return probabilistic_sharpe_ratio(
            observed_sharpe,
            n_obs=n_obs,
            benchmark_sharpe=0.0,
            skewness=skewness,
            excess_kurtosis=excess_kurtosis,
        )
    if variance_of_sharpes is None or variance_of_sharpes <= 0.0:
        variance_of_sharpes = 1.0 / max(1, n_obs - 1)
    z_alpha_n = (1.0 - _EULER_GAMMA) * _phi_inverse(1.0 - 1.0 / n_trials) + (
        _EULER_GAMMA * _phi_inverse(1.0 - 1.0 / (n_trials * math.e))
    )
    expected_max_sharpe = math.sqrt(variance_of_sharpes) * z_alpha_n
    return probabilistic_sharpe_ratio(
        observed_sharpe,
        n_obs=n_obs,
        benchmark_sharpe=expected_max_sharpe,
        skewness=skewness,
        excess_kurtosis=excess_kurtosis,
    )


def _phi_inverse(p: float) -> float:
    """Standard-normal inverse CDF via Beasley-Springer-Moro approximation."""
    if p <= 0.0 or p >= 1.0:
        return float("inf") if p >= 1.0 else float("-inf")
    # Beasley-Springer-Moro coefficients.
    a = [
        -3.969683028665376e1,
        2.209460984245205e2,
        -2.759285104469687e2,
        1.383577518672690e2,
        -3.066479806614716e1,
        2.506628277459239e0,
    ]
    b = [
        -5.447609879822406e1,
        1.615858368580409e2,
        -1.556989798598866e2,
        6.680131188771972e1,
        -1.328068155288572e1,
    ]
    c = [
        -7.784894002430293e-3,
        -3.223964580411365e-1,
        -2.400758277161838e0,
        -2.549732539343734e0,
        4.374664141464968e0,
        2.938163982698783e0,
    ]
    d = [
        7.784695709041462e-3,
        3.224671290700398e-1,
        2.445134137142996e0,
        3.754408661907416e0,
    ]
    p_low = 0.02425
    p_high = 1.0 - p_low
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (
            ((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]
        ) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
            * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
        )
    q = math.sqrt(-2 * math.log(1 - p))
    return -(
        ((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]
    ) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


__all__ = [
    "deflated_sharpe_ratio",
    "probabilistic_sharpe_ratio",
]
