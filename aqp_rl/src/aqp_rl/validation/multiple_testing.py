"""Multiple-testing corrections — Benjamini-Hochberg (FDR) + Holm-Bonferroni (FWER).

Both procedures take a vector of p-values and return a boolean
``reject`` mask. The Benjamini-Hochberg procedure controls the False
Discovery Rate (FDR) — the *expected proportion* of false discoveries
among the rejected hypotheses. The Holm-Bonferroni procedure controls
the Family-Wise Error Rate (FWER) — the probability of *any* false
discovery.

For a strategy-search context: prefer Benjamini-Hochberg when the
goal is to keep most discoveries true (allows a few false positives);
prefer Holm-Bonferroni when even a single false positive is costly
(e.g. promoting a strategy to live capital).
"""
from __future__ import annotations

import numpy as np


def benjamini_hochberg(
    p_values: np.ndarray,
    *,
    alpha: float = 0.05,
) -> dict[str, np.ndarray]:
    """Benjamini-Hochberg FDR correction.

    Parameters
    ----------
    p_values:
        ``(N,)`` array of p-values.
    alpha:
        FDR control level. Default ``0.05``.

    Returns
    -------
    dict with:
    - ``reject``: ``(N,)`` boolean mask — ``True`` ⇒ reject H_0.
    - ``adjusted``: ``(N,)`` BH-adjusted p-values (q-values).
    - ``threshold``: the BH p-value threshold actually applied.
    """
    p = np.asarray(p_values, dtype=np.float64)
    if p.ndim != 1:
        raise ValueError(f"p_values must be 1D; got {p.shape}")
    if not 0 < alpha < 1:
        raise ValueError(f"alpha must be in (0, 1); got {alpha!r}")
    n = len(p)
    if n == 0:
        return {
            "reject": np.zeros(0, dtype=bool),
            "adjusted": np.zeros(0, dtype=np.float64),
            "threshold": 0.0,
        }
    # Sort + rank.
    order = np.argsort(p)
    sorted_p = p[order]
    ranks = np.arange(1, n + 1, dtype=np.float64)
    thresholds = ranks / n * alpha
    # Largest k such that sorted_p[k] <= thresholds[k].
    below = sorted_p <= thresholds
    if below.any():
        k = int(np.where(below)[0].max())
        threshold = float(sorted_p[k])
    else:
        k = -1
        threshold = 0.0
    reject_sorted = np.zeros(n, dtype=bool)
    if k >= 0:
        reject_sorted[: k + 1] = True
    # Map back to original order.
    reject = np.zeros(n, dtype=bool)
    reject[order] = reject_sorted
    # BH-adjusted p-values (q-values).
    adj_sorted = np.minimum.accumulate((sorted_p * n / ranks)[::-1])[::-1]
    adj_sorted = np.minimum(adj_sorted, 1.0)
    adjusted = np.empty(n, dtype=np.float64)
    adjusted[order] = adj_sorted
    return {
        "reject": reject,
        "adjusted": adjusted,
        "threshold": threshold,
    }


def holm_bonferroni(
    p_values: np.ndarray,
    *,
    alpha: float = 0.05,
) -> dict[str, np.ndarray]:
    """Holm-Bonferroni FWER correction (step-down).

    Parameters
    ----------
    p_values:
        ``(N,)`` array of p-values.
    alpha:
        FWER control level. Default ``0.05``.

    Returns
    -------
    dict with:
    - ``reject``: ``(N,)`` boolean mask — ``True`` ⇒ reject H_0.
    - ``adjusted``: ``(N,)`` Holm-adjusted p-values.
    """
    p = np.asarray(p_values, dtype=np.float64)
    if p.ndim != 1:
        raise ValueError(f"p_values must be 1D; got {p.shape}")
    if not 0 < alpha < 1:
        raise ValueError(f"alpha must be in (0, 1); got {alpha!r}")
    n = len(p)
    if n == 0:
        return {
            "reject": np.zeros(0, dtype=bool),
            "adjusted": np.zeros(0, dtype=np.float64),
        }
    order = np.argsort(p)
    sorted_p = p[order]
    # Holm thresholds: alpha / (n - i) for the i-th smallest (0-indexed).
    thresholds = alpha / (n - np.arange(n, dtype=np.float64))
    reject_sorted = np.zeros(n, dtype=bool)
    # Step-down: stop at first failure.
    for i in range(n):
        if sorted_p[i] <= thresholds[i]:
            reject_sorted[i] = True
        else:
            break
    reject = np.zeros(n, dtype=bool)
    reject[order] = reject_sorted
    # Adjusted = min(1, max-so-far(p_i * (n - i))).
    adj_sorted = np.maximum.accumulate(sorted_p * (n - np.arange(n)))
    adj_sorted = np.minimum(adj_sorted, 1.0)
    adjusted = np.empty(n, dtype=np.float64)
    adjusted[order] = adj_sorted
    return {"reject": reject, "adjusted": adjusted}


__all__ = ["benjamini_hochberg", "holm_bonferroni"]
