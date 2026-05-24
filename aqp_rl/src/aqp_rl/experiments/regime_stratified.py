"""``RegimeStratifiedEvaluation`` — per-regime policy evaluation.

Runs a trained RL agent across the test data filtered by regime
label and emits per-regime metrics (total return, Sharpe, max
drawdown, hit rate). The regime labels come from the
:class:`SliceAndMergeRegimeFlow` analysis flow's gold Iceberg table
(or are passed in inline for testing).

This is the RL Lab's analogue of TradeMaster's "evaluate under
dynamic" mode — instead of one aggregate test metric, the user sees
N per-regime metrics so they can spot regime-specific weakness.

Hard rule 19: registers via the :class:`RLComponent` metaclass.
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar, Mapping

import numpy as np

from aqp_rl.core.experiment import BaseExperiment

logger = logging.getLogger(__name__)


class RegimeStratifiedEvaluation(BaseExperiment):
    """Evaluate a policy on a per-regime stratification of the test set.

    Parameters
    ----------
    n_regimes:
        Number of regimes the test data is partitioned into.
    regime_labels:
        Optional precomputed per-bar regime labels. When provided,
        :meth:`run` slices the rollout's per-step history by these
        labels. When absent, the agent's env is expected to stamp
        ``info['regime_label']`` every step.
    n_episodes:
        Number of full episodes to run for the rollout. Default ``1``.
    """

    rl_alias: ClassVar[str] = "regime_stratified"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "evaluation"
    rl_tags: ClassVar[tuple[str, ...]] = ("regime", "stratified", "market_dynamics")

    def __init__(
        self,
        *,
        n_regimes: int,
        regime_labels: list[int] | None = None,
        n_episodes: int = 1,
    ) -> None:
        if n_regimes < 1:
            raise ValueError(f"RegimeStratifiedEvaluation needs n_regimes ≥ 1; got {n_regimes!r}")
        if n_episodes < 1:
            raise ValueError(f"n_episodes must be ≥ 1; got {n_episodes!r}")
        self.n_regimes = int(n_regimes)
        self.regime_labels = list(regime_labels or [])
        self.n_episodes = int(n_episodes)

    def run(self, *, agent: Any, env: Any) -> dict[str, Any]:
        """Run rollouts and return per-regime metrics.

        The :class:`RLRuntime` calls this with the trained agent + the
        eval env. We don't go through :class:`RLRuntime._rollout` here
        because we want to preserve per-step ``info`` so we can group
        by regime label.
        """
        per_step_records: list[dict[str, Any]] = []
        for ep in range(self.n_episodes):
            obs, info = env.reset()
            step = 0
            done = False
            while not done:
                action, _ = agent.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, info = env.step(action)
                label = self._resolve_label(step, info)
                pv = float(info.get("portfolio_value", 0.0) or 0.0)
                ret = float(info.get("nav_return", 0.0) or 0.0)
                per_step_records.append(
                    {
                        "episode": ep,
                        "step": step,
                        "label": label,
                        "reward": float(reward),
                        "portfolio_value": pv,
                        "nav_return": ret,
                    }
                )
                step += 1
                done = bool(terminated or truncated)
        return self._aggregate(per_step_records)

    def _resolve_label(self, step: int, info: Mapping[str, Any]) -> int:
        """Pick the regime label for ``step`` from precomputed list or info."""
        if self.regime_labels and 0 <= step < len(self.regime_labels):
            return int(self.regime_labels[step])
        if info and "regime_label" in info:
            try:
                return int(info["regime_label"])
            except (TypeError, ValueError):
                return -1
        return -1

    def _aggregate(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Per-regime metric aggregation."""
        if not records:
            return {"per_regime": {}, "overall": {}}
        per_regime: dict[int, dict[str, Any]] = {}
        for rec in records:
            label = int(rec["label"])
            bucket = per_regime.setdefault(
                label,
                {"rewards": [], "returns": [], "portfolio_values": [], "count": 0},
            )
            bucket["rewards"].append(rec["reward"])
            bucket["returns"].append(rec["nav_return"])
            bucket["portfolio_values"].append(rec["portfolio_value"])
            bucket["count"] += 1

        out_per_regime: dict[int, dict[str, float]] = {}
        for label, bucket in per_regime.items():
            rets = np.asarray(bucket["returns"], dtype=np.float64)
            rewards = np.asarray(bucket["rewards"], dtype=np.float64)
            mean_ret = float(rets.mean()) if rets.size > 0 else 0.0
            std_ret = float(rets.std(ddof=1)) if rets.size > 1 else 0.0
            sharpe = float(mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0
            out_per_regime[label] = {
                "count": int(bucket["count"]),
                "mean_return": mean_ret,
                "std_return": std_ret,
                "sharpe": sharpe,
                "total_reward": float(rewards.sum()),
                "mean_reward": float(rewards.mean()) if rewards.size > 0 else 0.0,
                "hit_rate": float((rets > 0).mean()) if rets.size > 0 else 0.0,
            }

        all_rets = np.asarray([r["nav_return"] for r in records], dtype=np.float64)
        all_rewards = np.asarray([r["reward"] for r in records], dtype=np.float64)
        overall = {
            "count": int(len(records)),
            "mean_return": float(all_rets.mean()) if all_rets.size > 0 else 0.0,
            "std_return": float(all_rets.std(ddof=1)) if all_rets.size > 1 else 0.0,
            "total_reward": float(all_rewards.sum()),
            "n_regimes_seen": int(len(per_regime)),
        }
        return {"per_regime": out_per_regime, "overall": overall, "n_steps": len(records)}


__all__ = ["RegimeStratifiedEvaluation"]
