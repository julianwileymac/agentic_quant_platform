"""Rademacher Anti-Serum (RAS) — Paleologo 2024 §8.3.

**EXPERIMENTAL** — API is subject to change. See
:doc:`/architecture/decisions/008-rademacher-anti-serum` (planned)
for the stability roadmap.

The Rademacher Anti-Serum is a multiple-testing-aware correction to
the empirical Sharpe ratio. It subtracts three penalty terms:

1. **Rademacher complexity penalty** ``2 · R̂``: empirical Rademacher
   complexity of the strategy population, measuring how much the
   population can fit pure random noise.
2. **Finite-sample penalty** ``3 · sqrt(2 · ln(2 / δ) / T)``:
   standard concentration bound for the SR estimator.
3. **Multiple-testing penalty**
   ``sqrt(2 · ln(2 N / δ) / T)``: union bound across ``N``
   strategies.

The Rademacher complexity is estimated via Monte Carlo:

::

    R̂ = E_σ[ max_n (1/T) Σ_t σ_t · z_{t, n} ]

where ``σ`` are i.i.d. Rademacher random variables (``±1`` with
probability 1/2) and ``Z`` is the ``T × N`` returns matrix
(standardised).

The corrected SR lower bound is::

    θ_n ≥ θ̂_n − 2 R̂ − 3 sqrt(2 ln(2/δ) / T) − sqrt(2 ln(2N/δ) / T)

Reference: Paleologo, G.A. *Elements of Quantitative Investing*
(Wiley 2024), §8.3.
"""
from __future__ import annotations

import logging
import math

import numpy as np

logger = logging.getLogger(__name__)


def empirical_rademacher_complexity(
    returns_matrix: np.ndarray,
    *,
    n_draws: int = 1000,
    seed: int | None = 0,
) -> float:
    """Monte-Carlo estimate of the empirical Rademacher complexity.

    Parameters
    ----------
    returns_matrix:
        ``(T, N)`` matrix. Should be **standardised** (zero mean,
        unit std per column) so the Sharpe-ratio interpretation
        carries through.
    n_draws:
        Number of Monte-Carlo draws of the Rademacher vector.
    seed:
        RNG seed for reproducibility (``None`` ⇒ non-deterministic).

    Returns
    -------
    Float estimate of ``R̂``.
    """
    if returns_matrix.ndim != 2:
        raise ValueError(f"returns_matrix must be 2D; got {returns_matrix.shape}")
    T, N = returns_matrix.shape
    if T == 0 or N == 0:
        return 0.0
    rng = np.random.default_rng(seed)
    # Standardise so the complexity is on a comparable scale.
    z = (returns_matrix - returns_matrix.mean(axis=0)) / np.where(
        returns_matrix.std(axis=0, ddof=1) > 0,
        returns_matrix.std(axis=0, ddof=1),
        1.0,
    )
    # n_draws × T Rademacher matrix.
    sigmas = rng.choice([-1.0, 1.0], size=(n_draws, T)).astype(np.float64)
    # For each draw: σ @ z / T ⇒ (n_draws, N); take per-draw max over N.
    products = sigmas @ z / T  # (n_draws, N)
    per_draw_max = products.max(axis=1)
    return float(per_draw_max.mean())


def rademacher_anti_serum(
    returns_matrix: np.ndarray,
    *,
    empirical_sharpe: float,
    n_strategies_tested: int | None = None,
    confidence: float = 0.05,
    n_draws: int = 1000,
    seed: int | None = 0,
) -> dict[str, float]:
    """Compute the Rademacher Anti-Serum corrected lower bound.

    Parameters
    ----------
    returns_matrix:
        ``(T, N)`` matrix of strategy returns (one column per tested
        strategy in the search space).
    empirical_sharpe:
        The unannualised Sharpe ratio of the *winning* strategy
        (``θ̂_n``).
    n_strategies_tested:
        Override ``N`` (useful when ``returns_matrix`` is a smaller
        diagnostic sample). Defaults to ``returns_matrix.shape[1]``.
    confidence:
        Significance level ``δ ∈ (0, 1)``. Default ``0.05`` (95% CI).
    n_draws:
        Monte-Carlo draws for the Rademacher complexity estimate.

    Returns
    -------
    dict with ``corrected``, ``rademacher_penalty``,
    ``finite_sample_penalty``, ``multiple_testing_penalty``, and
    ``rademacher_complexity``.
    """
    if returns_matrix.ndim != 2:
        raise ValueError(f"returns_matrix must be 2D; got {returns_matrix.shape}")
    if not 0 < confidence < 1:
        raise ValueError(f"confidence δ must be in (0, 1); got {confidence!r}")
    T, default_N = returns_matrix.shape
    N = int(n_strategies_tested if n_strategies_tested is not None else default_N)
    if N < 1:
        raise ValueError(f"n_strategies_tested must be ≥ 1; got {N!r}")
    if T < 2:
        return {
            "corrected": float(empirical_sharpe),
            "rademacher_penalty": 0.0,
            "finite_sample_penalty": 0.0,
            "multiple_testing_penalty": 0.0,
            "rademacher_complexity": 0.0,
        }
    R_hat = empirical_rademacher_complexity(
        returns_matrix, n_draws=n_draws, seed=seed
    )
    rademacher_penalty = 2.0 * R_hat
    finite_sample_penalty = 3.0 * math.sqrt(2.0 * math.log(2.0 / confidence) / T)
    multiple_testing_penalty = math.sqrt(2.0 * math.log(2.0 * N / confidence) / T)
    corrected = float(
        empirical_sharpe - rademacher_penalty - finite_sample_penalty - multiple_testing_penalty
    )
    return {
        "corrected": corrected,
        "rademacher_penalty": float(rademacher_penalty),
        "finite_sample_penalty": float(finite_sample_penalty),
        "multiple_testing_penalty": float(multiple_testing_penalty),
        "rademacher_complexity": float(R_hat),
    }


__all__ = [
    "empirical_rademacher_complexity",
    "rademacher_anti_serum",
]
