"""``RewardAblationExperiment`` — sweep over reward-term weights.

For each ablation, the experiment zeroes one reward term (or all but
one) and trains the same agent. Useful for measuring the impact of
each component on the final equity curve.
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

from aqp.rl.core.experiment import BaseExperiment

logger = logging.getLogger(__name__)


class RewardAblationExperiment(BaseExperiment):
    """Train one agent per ablation pattern (single-term, leave-one-out)."""

    rl_alias: ClassVar[str] = "RewardAblationExperiment"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "ablation"
    rl_tags: ClassVar[tuple[str, ...]] = ("research",)

    def __init__(self, *, mode: str = "single-term") -> None:
        super().__init__()
        self.mode = str(mode)
        if self.mode not in {"single-term", "leave-one-out"}:
            raise ValueError(f"Unknown ablation mode: {self.mode!r}")

    def run(self, spec: Any, runtime: Any) -> dict[str, Any]:
        reward = spec.reward.spec if spec.reward else None
        if not reward or not isinstance(reward, dict):
            raise ValueError("RewardAblationExperiment requires spec.reward to be set")
        terms = list(reward.get("kwargs", {}).get("terms", []))
        if not terms:
            raise ValueError("Reward composite has no terms to ablate")
        results: list[dict[str, Any]] = []
        for idx, term in enumerate(terms):
            ablated = list(terms)
            if self.mode == "single-term":
                ablated = [term]
                tag = f"only-{term.get('class', idx)}"
            else:
                ablated = [t for j, t in enumerate(terms) if j != idx]
                tag = f"without-{term.get('class', idx)}"
            new_reward = {**reward}
            new_reward.setdefault("kwargs", {})["terms"] = ablated
            try:
                data = spec.model_dump(mode="python")
            except Exception:  # noqa: BLE001
                data = dict(getattr(spec, "__dict__", {}))
            data["reward"] = {"spec": new_reward}
            cls = type(spec)
            ablated_spec = cls.model_validate(data)
            try:
                runtime.spec = ablated_spec
                outcome = runtime._do_train(run_name=f"{spec.slug}-{tag}", overrides={})  # noqa: SLF001
                results.append({"tag": tag, "outcome": outcome})
            except Exception:  # noqa: BLE001
                logger.exception("ablation '%s' failed", tag)
        return {"mode": self.mode, "ablations": results}


__all__ = ["RewardAblationExperiment"]
