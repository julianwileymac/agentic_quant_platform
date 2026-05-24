"""Probability of Backtest Overfitting (PBO) via CSCV.

Reference: Bailey, D.H., J. Borwein, M. López de Prado, Q.J. Zhu
(2015), "The Probability of Backtest Overfitting", *Journal of
Computational Finance* 20 (4), 39-69.

Algorithm
=========

1. Stack ``N`` strategies' return time-series into a matrix
   ``M ∈ ℝ^{T × N}``.
2. Partition ``T`` rows into ``S`` equal-sized non-overlapping blocks
   (``S`` even, default 16).
3. For each of the ``C(S, S/2)`` IS/OOS splits:
   - Compute each strategy's IS performance metric.
   - Take ``j* = argmax_j IS_j``.
   - Compute that strategy's OOS performance metric.
   - Compute the OOS *rank* of strategy ``j*``: ``r_{j*} / (N + 1)``.
   - Logit: ``ℓ = ln(r / (1 - r))``.
4. **PBO** = fraction of splits where ``ℓ < 0`` (i.e. the in-sample
   best strategy ranked below median out-of-sample).

Returns
=======

A dict with:

- ``pbo``: ``∈ [0, 1]`` — the headline probability.
- ``logits``: per-split logits.
- ``n_splits``: total number of IS/OOS combinations.
- ``n_strategies``: ``N``.
"""
from __future__ import annotations

import logging
from itertools import combinations
from math import comb
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)


def _default_metric(returns: np.ndarray) -> np.ndarray:
    """Per-strategy Sharpe ratio (mean / std, unannualised)."""
    mean = returns.mean(axis=0)
    std = returns.std(axis=0, ddof=1)
    out = np.where(std > 0, mean / std, 0.0)
    return out


def probability_of_backtest_overfitting(
    returns_matrix: np.ndarray,
    *,
    n_blocks: int = 16,
    metric: Callable[[np.ndarray], np.ndarray] | None = None,
) -> dict[str, object]:
    """Compute the Probability of Backtest Overfitting.

    Parameters
    ----------
    returns_matrix:
        ``(T, N)`` matrix of per-strategy per-period returns.
    n_blocks:
        Number of non-overlapping blocks (``S``). Must be even. Larger
        ``S`` ⇒ more IS/OOS combinations ⇒ tighter PBO estimate, at
        the cost of needing more data per block.
    metric:
        Callable ``returns -> per-strategy score``. Default Sharpe
        (mean / std, unannualised).

    Returns
    -------
    dict with ``pbo``, ``logits``, ``n_splits``, ``n_strategies``.
    """
    if returns_matrix.ndim != 2:
        raise ValueError(f"returns_matrix must be 2D; got shape {returns_matrix.shape}")
    if n_blocks < 2 or n_blocks % 2 != 0:
        raise ValueError(f"n_blocks must be an even integer ≥ 2; got {n_blocks!r}")
    metric_fn = metric or _default_metric
    T, N = returns_matrix.shape
    if T < n_blocks:
        raise ValueError(
            f"returns_matrix has T={T} rows but n_blocks={n_blocks}; need T ≥ n_blocks"
        )
    block_size = T // n_blocks
    if block_size < 1:
        raise ValueError("each block must hold ≥ 1 row")
    # Split rows into ``n_blocks`` blocks.
    block_indices: list[np.ndarray] = []
    for b in range(n_blocks):
        start = b * block_size
        end = T if b == n_blocks - 1 else (b + 1) * block_size
        block_indices.append(np.arange(start, end))

    logits: list[float] = []
    is_size = n_blocks // 2
    for is_blocks in combinations(range(n_blocks), is_size):
        oos_blocks = tuple(b for b in range(n_blocks) if b not in is_blocks)
        is_idx = np.concatenate([block_indices[b] for b in is_blocks])
        oos_idx = np.concatenate([block_indices[b] for b in oos_blocks])
        is_scores = metric_fn(returns_matrix[is_idx])
        oos_scores = metric_fn(returns_matrix[oos_idx])
        best_is = int(np.argmax(is_scores))
        # OOS rank of the best-IS strategy (rank = position from worst → best).
        oos_rank = float(np.searchsorted(np.sort(oos_scores), oos_scores[best_is]) + 1)
        normalised_rank = oos_rank / (N + 1)
        # Logit; guarded.
        eps = 1e-9
        normalised_rank = float(np.clip(normalised_rank, eps, 1.0 - eps))
        logit = float(np.log(normalised_rank / (1.0 - normalised_rank)))
        logits.append(logit)

    logits_arr = np.asarray(logits, dtype=np.float64)
    pbo = float((logits_arr < 0).mean()) if len(logits_arr) > 0 else 0.0
    return {
        "pbo": pbo,
        "logits": logits_arr,
        "n_splits": int(comb(n_blocks, is_size)),
        "n_strategies": int(N),
    }


__all__ = ["probability_of_backtest_overfitting"]
