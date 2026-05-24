"""``ValidationExperiment`` — CPCV + PBO + RAS + DSR diagnostic suite.

Runs the canonical selection-bias-aware validation pipeline over a
trained agent's per-strategy returns matrix and emits a single
report dict that the :class:`RLRuntime` persists into the
``rl_runs.result_summary`` JSON column.

The experiment is *agent-agnostic* — it takes a precomputed
``returns_matrix`` (``T × N`` per-strategy per-period returns) and a
winning-strategy index. Callers typically obtain the matrix by
running an :class:`aqp_rl.ensemblers.walk_forward.WalkForwardEnsembler`
across the search space.

Hard rule 19: registers via the :class:`RLComponent` metaclass.
Hard rule 17: emitted ``returns_matrix_hash`` lets the snapshot stay
hash-locked even when the validation suite is re-run.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, ClassVar

import numpy as np

from aqp_rl.core.experiment import BaseExperiment
from aqp_rl.validation.cpcv import (
    CombinatorialPurgedKFold,
    combinatorial_paths_count,
)
from aqp_rl.validation.deflated_sharpe import deflated_sharpe_ratio
from aqp_rl.validation.pbo import probability_of_backtest_overfitting
from aqp_rl.validation.rademacher import rademacher_anti_serum

logger = logging.getLogger(__name__)


class ValidationExperiment(BaseExperiment):
    """Run the full PBO + RAS + DSR + CPCV suite over a returns matrix.

    Parameters
    ----------
    n_splits, n_test_splits:
        CPCV configuration. Default (10, 2) ⇒ ``φ(10, 2) = 9`` paths.
    pbo_n_blocks:
        Block count for the PBO CSCV. Default ``16``.
    confidence:
        Significance level shared by RAS and DSR. Default ``0.05``.
    rademacher_draws:
        Monte-Carlo draws for the RAS Rademacher complexity estimate.
        Default ``500``.
    """

    rl_alias: ClassVar[str] = "validation_suite"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "validation"
    rl_tags: ClassVar[tuple[str, ...]] = (
        "cpcv",
        "pbo",
        "rademacher",
        "deflated_sharpe",
        "selection_bias",
    )

    def __init__(
        self,
        *,
        n_splits: int = 10,
        n_test_splits: int = 2,
        pbo_n_blocks: int = 16,
        confidence: float = 0.05,
        rademacher_draws: int = 500,
    ) -> None:
        self.n_splits = int(n_splits)
        self.n_test_splits = int(n_test_splits)
        self.pbo_n_blocks = int(pbo_n_blocks)
        self.confidence = float(confidence)
        self.rademacher_draws = int(rademacher_draws)

    def run(
        self,
        *,
        returns_matrix: np.ndarray,
        winning_strategy_idx: int | None = None,
        annualisation_factor: float = 1.0,
    ) -> dict[str, Any]:
        """Run the full diagnostic suite and return a report dict."""
        if returns_matrix.ndim != 2:
            raise ValueError(
                f"returns_matrix must be 2D; got {returns_matrix.shape}"
            )
        T, N = returns_matrix.shape
        # Per-strategy unannualised Sharpe.
        mean = returns_matrix.mean(axis=0)
        std = returns_matrix.std(axis=0, ddof=1)
        sr = np.where(std > 0, mean / std, 0.0)
        if winning_strategy_idx is None:
            winning_strategy_idx = int(np.argmax(sr))
        sr_hat = float(sr[int(winning_strategy_idx)])
        winning_returns = returns_matrix[:, int(winning_strategy_idx)]

        # CPCV — pure path-counter for the diagnostic surface (the
        # caller has already trained-and-eval'd per fold to fill in
        # ``returns_matrix``; here we just report the path count).
        cpcv_paths = combinatorial_paths_count(self.n_splits, self.n_test_splits)

        # PBO — requires T ≥ pbo_n_blocks.
        try:
            pbo_result = probability_of_backtest_overfitting(
                returns_matrix,
                n_blocks=min(self.pbo_n_blocks, T - (T % 2)),
            )
        except Exception:  # noqa: BLE001
            logger.exception("PBO computation failed")
            pbo_result = {"pbo": float("nan"), "logits": np.zeros(0), "n_splits": 0}

        # RAS lower bound on the winning strategy's SR.
        try:
            ras_result = rademacher_anti_serum(
                returns_matrix,
                empirical_sharpe=sr_hat,
                n_strategies_tested=N,
                confidence=self.confidence,
                n_draws=self.rademacher_draws,
            )
        except Exception:  # noqa: BLE001
            logger.exception("RAS computation failed")
            ras_result = {"corrected": sr_hat, "rademacher_penalty": 0.0}

        # DSR — probability that the true Sharpe is > 0.
        try:
            dsr = deflated_sharpe_ratio(
                winning_returns,
                sr_hat=sr_hat,
                sr_list=sr.tolist(),
                n_strategies_tested=N,
            )
        except Exception:  # noqa: BLE001
            logger.exception("DSR computation failed")
            dsr = float("nan")

        return {
            "winning_strategy_idx": int(winning_strategy_idx),
            "sr_hat": sr_hat,
            "sr_hat_annualised": sr_hat * float(annualisation_factor),
            "cpcv": {
                "n_splits": self.n_splits,
                "n_test_splits": self.n_test_splits,
                "n_backtest_paths": cpcv_paths,
            },
            "pbo": float(pbo_result["pbo"]),
            "pbo_n_splits": int(pbo_result.get("n_splits", 0)),
            "rademacher": {
                "corrected_sr_lower_bound": float(ras_result["corrected"]),
                "rademacher_penalty": float(ras_result.get("rademacher_penalty", 0.0)),
                "finite_sample_penalty": float(ras_result.get("finite_sample_penalty", 0.0)),
                "multiple_testing_penalty": float(ras_result.get("multiple_testing_penalty", 0.0)),
            },
            "deflated_sharpe_ratio": float(dsr),
            "returns_matrix_hash": _hash_returns(returns_matrix),
            "T": int(T),
            "N": int(N),
        }


def _hash_returns(returns_matrix: np.ndarray) -> str:
    """SHA-256 of the float64-serialised returns matrix (stable hash)."""
    arr = np.ascontiguousarray(returns_matrix, dtype=np.float64)
    return hashlib.sha256(arr.tobytes()).hexdigest()


__all__ = ["ValidationExperiment"]
