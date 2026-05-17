"""``ReinforcePlusPlusAdvantage`` — native port of NeMo-RL's REINFORCE++.

Math comes from NVIDIA-NeMo/RL
``algorithms/utils.py::calculate_baseline_and_std_per_prompt`` +
``algorithms/utils.py::masked_mean(..., global_normalization_factor=...)``
(commit 20d46a7d1bd987df1c89b3c5a81dc945c3d201e4). The "prompt group"
abstraction from NLP rollouts maps directly onto AQP's "parallel-RL
cohort": every rollout that starts at the same environment seed in
the same temporal window shares a cohort id, and the cohort mean is
the local baseline.

Cohort baseline (RLOO style)
----------------------------

For each cohort ``g``::

    prompt_baseline_g = matmul((1 - I), rewards_g) / (N_g - 1)

i.e. each transition's baseline is the mean reward of the OTHER N-1
transitions in its cohort (leave-one-out).

Decoupled global normalisation
------------------------------

After subtracting the local baseline we normalise by the **global**
batch std::

    advantages = (rewards - baseline) / (global_std + eps)

This is the crucial "minus_baseline + global normalization"
decoupling — when ``global_normalization=True`` the advantage signal
is invariant to systemic regime shifts that hit every cohort at
once (e.g. a flash crash on day 73 of training). The local baseline
preserves the relative outperformance signal; the global
normalisation collapses the variance shift across cohorts.

Stop-properly diagnostics
-------------------------

This estimator does not apply the ``stop_properly_penalty_coef`` —
that is :class:`StopProperlyShaping`'s job. It does count + emit
the truncation rate so logs / dashboards can correlate the rate
with policy regression.
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

import numpy as np

from aqp.rl.advantage.base import AdvantageOutput, BaseAdvantageEstimator

logger = logging.getLogger(__name__)


class ReinforcePlusPlusAdvantage(BaseAdvantageEstimator):
    """Leave-one-out cohort baseline with decoupled global normalisation.

    Parameters
    ----------
    minus_baseline:
        When ``True`` (default) subtract the leave-one-out cohort
        baseline from the reward. ``False`` falls back to raw rewards
        — useful as an ablation toggle. Matches the NeMo-RL
        ``minus_baseline`` YAML flag.
    global_normalization:
        When ``True`` (default) divide the centred advantage by the
        global batch std (computed across every cohort). When
        ``False`` we divide by the per-cohort std — the FinRL-style
        approach that does NOT decouple variance shifts.
    leave_one_out:
        When ``True`` (default) the baseline excludes the sample its
        being computed for (RLOO, arxiv 2402.14740). When ``False``
        the cohort mean includes the sample.
    eps:
        Numerical-stability epsilon. Matches NeMo-RL's ``1e-8``.

    Notes
    -----
    Returns equal cumulative reward-to-go (no discount inside the
    cohort — the cohort is one episode's worth of transitions).
    Discounting is applied upstream by the env / reward stack if
    desired.
    """

    rl_alias: ClassVar[str] = "ReinforcePlusPlus"
    rl_source: ClassVar[str] = "nemo_rl"
    rl_category: ClassVar[str] = "policy_gradient"
    rl_tags: ClassVar[tuple[str, ...]] = (
        "reinforce_plus_plus",
        "rloo",
        "cohort_baseline",
        "global_normalization",
    )

    def __init__(
        self,
        *,
        minus_baseline: bool = True,
        global_normalization: bool = True,
        leave_one_out: bool = True,
        eps: float = 1e-8,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name)
        self.minus_baseline = bool(minus_baseline)
        self.global_normalization = bool(global_normalization)
        self.leave_one_out = bool(leave_one_out)
        self.eps = float(eps)

    def compute(
        self,
        *,
        rewards: np.ndarray,
        values: np.ndarray | None = None,
        dones: np.ndarray | None = None,
        truncated: np.ndarray | None = None,
        group_ids: np.ndarray | None = None,
        valid_mask: np.ndarray | None = None,
    ) -> AdvantageOutput:
        rewards_arr = np.asarray(rewards, dtype=np.float64).ravel()
        n = len(rewards_arr)
        if n == 0:
            return AdvantageOutput(
                advantages=np.zeros(0, dtype=np.float64),
                returns=np.zeros(0, dtype=np.float64),
                baselines=np.zeros(0, dtype=np.float64),
                std=None,
                extras={"truncation_rate": 0.0, "num_groups": 0},
            )
        if group_ids is None:
            # Single cohort: every transition shares the same baseline.
            group_ids_arr = np.zeros(n, dtype=np.int64)
        else:
            group_ids_arr = np.asarray(group_ids, dtype=np.int64).ravel()
            if len(group_ids_arr) != n:
                raise ValueError(
                    f"group_ids length {len(group_ids_arr)} != rewards length {n}"
                )
        if valid_mask is None:
            valid_mask_arr = np.ones(n, dtype=np.float64)
        else:
            valid_mask_arr = np.asarray(valid_mask, dtype=np.float64).ravel()

        baselines, stds = self._cohort_baseline_and_std(rewards_arr, group_ids_arr, valid_mask_arr)

        # Centred rewards.
        if self.minus_baseline:
            centred = rewards_arr - baselines
        else:
            centred = rewards_arr

        # Decoupled global vs local normalisation.
        if self.global_normalization:
            denom = float(np.std(centred, ddof=1)) if n > 1 else 0.0
        else:
            denom = float(np.mean(stds)) if len(stds) > 0 else 0.0
        denom = max(denom, self.eps)

        advantages = centred / denom

        truncation_rate = 0.0
        if truncated is not None:
            truncated_arr = np.asarray(truncated, dtype=bool).ravel()
            if len(truncated_arr) == n:
                truncation_rate = float(truncated_arr.mean())

        return AdvantageOutput(
            advantages=advantages.astype(np.float64),
            returns=rewards_arr,
            baselines=baselines,
            std=stds,
            extras={
                "truncation_rate": truncation_rate,
                "num_groups": int(np.unique(group_ids_arr).size),
                "global_std": denom,
                "minus_baseline": self.minus_baseline,
                "global_normalization": self.global_normalization,
            },
        )

    # ------------------------------------------------------------------ baseline math

    def _cohort_baseline_and_std(
        self,
        rewards: np.ndarray,
        group_ids: np.ndarray,
        valid_mask: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Replicates NeMo-RL ``calculate_baseline_and_std_per_prompt``.

        Returns ``(baselines, stds)`` aligned with ``rewards``. Each
        element is the leave-one-out cohort baseline (or cohort mean
        when ``leave_one_out=False``) and the cohort standard
        deviation.
        """
        baseline = np.zeros_like(rewards)
        std = np.zeros_like(rewards)
        unique_groups = np.unique(group_ids)
        for g in unique_groups:
            mask = group_ids == g
            idx = np.flatnonzero(mask)
            if len(idx) == 0:
                continue
            r_g = rewards[idx]
            v_g = valid_mask[idx]
            if v_g.sum() <= 1:
                # Match NeMo-RL behaviour: insufficient valid responses,
                # set baseline = reward (so advantage = 0).
                baseline[idx] = r_g
                continue
            if self.leave_one_out:
                # Equivalent to NeMo-RL's matmul((1 - I), r * v) / (sum(v) - 1).
                # Each entry's baseline is the mean of the OTHER N-1 entries
                # weighted by their validity.
                weighted_sum = float(np.sum(r_g * v_g))
                denom = float(v_g.sum()) - 1.0
                if denom <= 0:
                    baseline[idx] = r_g
                    continue
                # baseline_i = (sum - r_i * v_i) / denom for each i
                per_entry_excluded = weighted_sum - r_g * v_g
                baseline[idx] = per_entry_excluded / denom
                sq_per_entry = float(np.sum((r_g ** 2) * v_g)) - (r_g ** 2) * v_g
                var = sq_per_entry / denom - (baseline[idx] ** 2)
                var = np.clip(var, 0.0, None)
                # NeMo-RL applies the bessel correction num_valid / (num_valid - 1)
                bessel = denom / max(denom - 1.0, self.eps) if denom > 1.0 else 1.0
                std[idx] = np.sqrt(var * bessel)
            else:
                denom = float(v_g.sum())
                mean = float(np.sum(r_g * v_g)) / max(denom, self.eps)
                baseline[idx] = mean
                var = float(np.sum(((r_g - mean) ** 2) * v_g)) / max(denom - 1.0, self.eps)
                std[idx] = np.sqrt(max(var, 0.0))
        return baseline, std

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out.update(
            {
                "minus_baseline": self.minus_baseline,
                "global_normalization": self.global_normalization,
                "leave_one_out": self.leave_one_out,
                "eps": self.eps,
            }
        )
        return out


__all__ = ["ReinforcePlusPlusAdvantage"]
