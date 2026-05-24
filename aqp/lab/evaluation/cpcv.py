"""Combinatorial Purged Cross-Validation (López de Prado, 2018).

Standard k-fold leaks in financial time series because labels (e.g.
triple-barrier targets) overlap. CPCV solves this by partitioning the
data into ``n_folds`` groups, choosing every ``C(n_folds,
n_test_folds)`` combination of test folds, then purging + embargoing
the training rows whose labels overlap the test set.

The path-count grows combinatorially: ``C(10, 2) = 45``, ``C(20, 5)
= 15504``. The plan §13 risk register sets a HARD GUARD of 100 paths
unless the operator explicitly overrides — :class:`CPCVPlanError`
fires on the soft limit; the runner asks for explicit confirmation
above it.

The implementation produces deterministic, JSON-serialisable
:class:`CPCVPath` objects so the sweep controller can dispatch one
Celery child run per path with the same content hash.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import combinations
from typing import Iterable


# Default CPCV parameters per López de Prado + the plan's §16 default.
DEFAULT_N_FOLDS = 6
DEFAULT_N_TEST_FOLDS = 2
DEFAULT_EMBARGO_PCT = 1.0
DEFAULT_HARD_GUARD_PATHS = 100


class CPCVPlanError(ValueError):
    """Raised when the planned CPCV path count exceeds the safety guard."""


@dataclass(frozen=True)
class CPCVConfig:
    n_folds: int = DEFAULT_N_FOLDS
    n_test_folds: int = DEFAULT_N_TEST_FOLDS
    embargo_pct: float = DEFAULT_EMBARGO_PCT
    purge_size: int = 0  # rows; defaults to the max label horizon at runtime
    hard_guard_paths: int = DEFAULT_HARD_GUARD_PATHS
    explicit_high_path_count_ok: bool = False


@dataclass(frozen=True)
class CPCVPath:
    """One (train_indices, test_indices) split."""

    path_id: int
    train: tuple[int, ...]
    test: tuple[int, ...]
    test_folds: tuple[int, ...]


def safe_cpcv_path_count(n_folds: int, n_test_folds: int) -> int:
    """Return ``C(n_folds, n_test_folds)`` — the planned path count.

    Pure function — used by the route layer to render a friction
    dialog before kicking off a high-cost evaluation.
    """
    if n_folds < n_test_folds or n_test_folds < 1:
        return 0
    return math.comb(n_folds, n_test_folds)


def combinatorial_purged_cv(
    n_observations: int,
    config: CPCVConfig | None = None,
) -> list[CPCVPath]:
    """Generate the CPCV splits over ``n_observations`` rows.

    Raises :class:`CPCVPlanError` when the planned path count exceeds
    ``hard_guard_paths`` and the operator did not opt-in via
    ``explicit_high_path_count_ok=True``.
    """
    cfg = config or CPCVConfig()
    if n_observations < cfg.n_folds:
        raise ValueError(
            f"CPCV needs at least n_folds={cfg.n_folds} observations "
            f"(got {n_observations})"
        )
    if cfg.n_test_folds < 1 or cfg.n_test_folds >= cfg.n_folds:
        raise ValueError(
            f"n_test_folds must be in [1, n_folds-1]; got {cfg.n_test_folds}"
        )

    planned_paths = safe_cpcv_path_count(cfg.n_folds, cfg.n_test_folds)
    if planned_paths > cfg.hard_guard_paths and not cfg.explicit_high_path_count_ok:
        raise CPCVPlanError(
            f"CPCV plan would generate {planned_paths} paths "
            f"(hard guard is {cfg.hard_guard_paths}); set "
            f"explicit_high_path_count_ok=True to proceed."
        )

    # Partition observations into ``n_folds`` contiguous groups.
    fold_size = n_observations // cfg.n_folds
    embargo = max(1, int(n_observations * cfg.embargo_pct / 100.0)) if cfg.embargo_pct else 0
    purge = max(0, int(cfg.purge_size))

    fold_ranges: list[tuple[int, int]] = []
    start = 0
    for f in range(cfg.n_folds):
        end = start + fold_size if f < cfg.n_folds - 1 else n_observations
        fold_ranges.append((start, end))
        start = end

    paths: list[CPCVPath] = []
    for path_id, test_folds in enumerate(combinations(range(cfg.n_folds), cfg.n_test_folds)):
        test_indices: list[int] = []
        for f in test_folds:
            test_indices.extend(range(*fold_ranges[f]))
        # Train indices are everything else minus purge + embargo
        # around each test fold range.
        purged: set[int] = set()
        for f in test_folds:
            lo, hi = fold_ranges[f]
            purged.update(range(max(0, lo - purge), lo))
            purged.update(range(hi, min(n_observations, hi + purge + embargo)))
        all_indices = set(range(n_observations))
        train_indices = sorted(all_indices - set(test_indices) - purged)
        paths.append(
            CPCVPath(
                path_id=path_id,
                train=tuple(train_indices),
                test=tuple(test_indices),
                test_folds=tuple(test_folds),
            )
        )
    return paths


__all__ = [
    "CPCVConfig",
    "CPCVPath",
    "CPCVPlanError",
    "DEFAULT_EMBARGO_PCT",
    "DEFAULT_HARD_GUARD_PATHS",
    "DEFAULT_N_FOLDS",
    "DEFAULT_N_TEST_FOLDS",
    "combinatorial_purged_cv",
    "safe_cpcv_path_count",
]
