"""``GAEAdvantage`` — Generalised Advantage Estimation (Schulman 2016).

Critic-based advantage with the canonical lambda-mixing formula::

    delta_t = r_t + gamma * V(s_{t+1}) * (1 - d_t) - V(s_t)
    A_t = delta_t + gamma * lambda * A_{t+1} * (1 - d_t)

Kept as a registered option so the spec-driven flow can pick GAE
when a critic is available (SB3 PPO / CleanRL PPO with value head)
without having to fork the runtime / agent adapter.
"""
from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from aqp.rl.advantage.base import AdvantageOutput, BaseAdvantageEstimator


class GAEAdvantage(BaseAdvantageEstimator):
    """Critic-based generalised advantage estimation."""

    rl_alias: ClassVar[str] = "GAE"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "policy_gradient"
    rl_tags: ClassVar[tuple[str, ...]] = ("gae", "critic", "actor_critic")

    def __init__(
        self,
        *,
        gamma: float = 0.99,
        lam: float = 0.95,
        normalise: bool = True,
        eps: float = 1e-8,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name)
        self.gamma = float(gamma)
        self.lam = float(lam)
        self.normalise = bool(normalise)
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
        if values is None:
            raise ValueError("GAEAdvantage requires a `values` tensor")
        rewards_arr = np.asarray(rewards, dtype=np.float64).ravel()
        values_arr = np.asarray(values, dtype=np.float64).ravel()
        n = len(rewards_arr)
        if n == 0:
            return AdvantageOutput(
                advantages=np.zeros(0, dtype=np.float64),
                returns=np.zeros(0, dtype=np.float64),
            )
        if dones is None:
            dones_arr = np.zeros(n, dtype=np.float64)
        else:
            dones_arr = np.asarray(dones, dtype=np.float64).ravel()
        # Pad values with one extra entry for the terminal bootstrap.
        if len(values_arr) == n:
            values_padded = np.concatenate([values_arr, np.zeros(1, dtype=np.float64)])
        else:
            values_padded = values_arr
        advantages = np.zeros(n, dtype=np.float64)
        last_adv = 0.0
        for t in reversed(range(n)):
            mask = 1.0 - float(dones_arr[t])
            delta = rewards_arr[t] + self.gamma * values_padded[t + 1] * mask - values_padded[t]
            last_adv = delta + self.gamma * self.lam * mask * last_adv
            advantages[t] = last_adv
        returns = advantages + values_padded[:n]
        if self.normalise and n > 1:
            mean = float(advantages.mean())
            std = float(advantages.std(ddof=1))
            advantages = (advantages - mean) / max(std, self.eps)
        truncation_rate = 0.0
        if truncated is not None:
            truncated_arr = np.asarray(truncated, dtype=bool).ravel()
            if len(truncated_arr) == n:
                truncation_rate = float(truncated_arr.mean())
        return AdvantageOutput(
            advantages=advantages,
            returns=returns,
            baselines=values_padded[:n],
            std=None,
            extras={
                "gamma": self.gamma,
                "lam": self.lam,
                "normalise": self.normalise,
                "truncation_rate": truncation_rate,
            },
        )

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out.update(
            {"gamma": self.gamma, "lam": self.lam, "normalise": self.normalise, "eps": self.eps}
        )
        return out


__all__ = ["GAEAdvantage"]
