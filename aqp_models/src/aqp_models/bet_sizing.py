"""Position / bet sizing helpers (AFML ch. 10).

Three flavours covered:

* :func:`bet_size_probability` — convert a model's predicted probability
  into a continuous bet size via the ``2 * Φ⁻¹(p) / √h`` transform
  (where ``Φ`` is the normal CDF and ``h`` = forecast horizon).
* :func:`bet_size_budget` — given concurrent active bets, size each one
  so the portfolio's aggregate exposure respects a per-symbol cap.
* :func:`discrete_bet_size` — snap continuous sizes to a configurable
  step-size (e.g. 0.25 increments) for fills that must be nice round
  lot fractions.
* :func:`dynamic_bet_size` — trailing-stop-aware sizing that cuts the
  absolute bet size as MFE (max favourable excursion) grows.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def bet_size_probability(
    prob: pd.Series | np.ndarray,
    side: pd.Series | np.ndarray | None = None,
    num_classes: int = 2,
) -> pd.Series:
    """Signed bet size from classifier probabilities.

    ``z`` = (p − 1/K) / √(p(1−p)) with ``K`` = num_classes.
    ``bet = side × (2 Φ(z) − 1)`` ∈ [-1, 1].
    """
    prob = pd.Series(prob) if not isinstance(prob, pd.Series) else prob
    if side is None:
        side = pd.Series(1.0, index=prob.index)
    elif not isinstance(side, pd.Series):
        side = pd.Series(side, index=prob.index)
    p = prob.clip(1e-8, 1 - 1e-8)
    sigma = np.sqrt(p * (1 - p))
    z = (p - 1.0 / num_classes) / sigma
    bet = side * (2 * stats.norm.cdf(z) - 1)
    return bet.rename("bet_size")


def discrete_bet_size(bet: pd.Series, step: float = 0.05) -> pd.Series:
    """Snap continuous bets to multiples of ``step``."""
    if step <= 0:
        return bet
    return (np.round(bet / step) * step).astype(float)


def bet_size_budget(bets: pd.DataFrame, max_concurrent: int | None = None) -> pd.Series:
    """Normalise concurrent bets so the portfolio's gross exposure ≤ 1.

    ``bets`` is expected to have one row per active bet with columns
    ``start``, ``end``, ``size``. Returns a Series of rescaled sizes.
    """
    if bets.empty:
        return pd.Series(dtype=float, name="bet_size")
    timeline = pd.concat(
        [
            pd.Series(1, index=pd.DatetimeIndex(bets["start"])),
            pd.Series(-1, index=pd.DatetimeIndex(bets["end"])),
        ]
    ).sort_index().cumsum()
    if max_concurrent is None:
        max_concurrent = int(timeline.max() or 1)
    adjusted = bets["size"] / max_concurrent
    return adjusted.rename("bet_size")


def dynamic_bet_size(
    bet: float,
    entry_price: float,
    current_price: float,
    mfe_haircut: float = 0.5,
) -> float:
    """Reduce the bet linearly with max-favourable-excursion."""
    if entry_price <= 0:
        return bet
    mfe = (current_price - entry_price) / entry_price
    haircut = max(0.0, mfe_haircut * mfe)
    return float(np.sign(bet) * max(0.0, abs(bet) - haircut))


__all__ = [
    "bet_size_budget",
    "bet_size_probability",
    "discrete_bet_size",
    "dynamic_bet_size",
]
