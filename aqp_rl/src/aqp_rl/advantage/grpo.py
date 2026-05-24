"""``GRPOAdvantage`` — Group Relative Policy Optimization (DeepSeek R1 / NeMo-RL).

GRPO is REINFORCE++ minus the leave-one-out twist: the baseline is
simply the cohort mean (not leave-one-out) and there is no critic.
Cohort-relative normalisation by per-cohort std is the canonical
form (the ``RLHF`` variant), matching the DeepSeek paper and
NeMo-RL's :mod:`nemo_rl.algorithms.grpo`.

We expose it as a distinct estimator (rather than a flag toggle on
:class:`ReinforcePlusPlusAdvantage`) so the registry can list it as a
separate option and so future GRPO-specific extras (e.g. trust-region
clipping, RM-blended baselines) have a clean home.
"""
from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from aqp_rl.advantage.base import AdvantageOutput, BaseAdvantageEstimator


class GRPOAdvantage(BaseAdvantageEstimator):
    """Group-relative no-critic advantage estimator.

    Parameters
    ----------
    normalise_by_cohort_std:
        When ``True`` (default) divide the centred reward by the
        per-cohort std (DeepSeek R1 form). When ``False`` divide by
        the global batch std (closer to the FinRL-X "single cohort"
        approximation).
    eps:
        Numerical-stability epsilon.
    """

    rl_alias: ClassVar[str] = "GRPO"
    rl_source: ClassVar[str] = "nemo_rl"
    rl_category: ClassVar[str] = "policy_gradient"
    rl_tags: ClassVar[tuple[str, ...]] = ("grpo", "group_relative", "no_critic")

    def __init__(
        self,
        *,
        normalise_by_cohort_std: bool = True,
        eps: float = 1e-8,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name)
        self.normalise_by_cohort_std = bool(normalise_by_cohort_std)
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
            )
        group_ids_arr = (
            np.asarray(group_ids, dtype=np.int64).ravel()
            if group_ids is not None
            else np.zeros(n, dtype=np.int64)
        )
        baselines = np.zeros_like(rewards_arr)
        stds = np.zeros_like(rewards_arr)
        for g in np.unique(group_ids_arr):
            mask = group_ids_arr == g
            r_g = rewards_arr[mask]
            mean_g = float(r_g.mean())
            std_g = float(r_g.std(ddof=1)) if len(r_g) > 1 else 0.0
            baselines[mask] = mean_g
            stds[mask] = std_g
        centred = rewards_arr - baselines
        if self.normalise_by_cohort_std:
            denom = np.maximum(stds, self.eps)
        else:
            global_std = float(np.std(centred, ddof=1)) if n > 1 else 0.0
            denom = np.full_like(rewards_arr, max(global_std, self.eps))
        advantages = centred / denom

        truncation_rate = 0.0
        if truncated is not None:
            truncated_arr = np.asarray(truncated, dtype=bool).ravel()
            if len(truncated_arr) == n:
                truncation_rate = float(truncated_arr.mean())
        return AdvantageOutput(
            advantages=advantages,
            returns=rewards_arr,
            baselines=baselines,
            std=stds,
            extras={
                "truncation_rate": truncation_rate,
                "num_groups": int(np.unique(group_ids_arr).size),
                "normalise_by_cohort_std": self.normalise_by_cohort_std,
            },
        )

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out.update(
            {
                "normalise_by_cohort_std": self.normalise_by_cohort_std,
                "eps": self.eps,
            }
        )
        return out


__all__ = ["GRPOAdvantage"]
