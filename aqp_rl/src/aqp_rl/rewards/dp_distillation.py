"""Dynamic-programming demonstration-distillation reward (HFT pattern).

Port of TradeMaster's ``HFTLoss``::

    HFTLoss(pred, target, distribution, demonstration) =
        MSE(pred, target) + ada · KL_div(softmax(distribution), demonstration)

In the HFT_DDQN agent the loss is computed during the gradient step.
At env-step time we surface the *reward-equivalent* contribution as
``−ada · KL(softmax(agent_distribution) || DP_demonstration)`` so the
loss surface composes cleanly with the rest of the per-step reward.

The agent (or a SB3/CleanRL callback) is expected to stamp
``info["agent_action_distribution"]`` — a per-step softmax over the
discrete action space — alongside the env's already-present
``info["DP_action"]`` (the DP-optimal one-hot the env computes once
at construction via ``making_multi_level_dp_demonstration``).

When either input is missing this term contributes zero — it composes
gracefully with envs that don't ship a DP oracle.

The KL is computed in nats with the convention ``KL(p || q) = Σ p ·
log(p / q)`` where ``p`` is the agent's softmax and ``q`` is the DP
demonstration. We add a small ``eps`` floor to both distributions to
avoid ``log(0)`` blow-ups when the DP picks a single action with
probability 1.

Hard rule 19: registered through :class:`RLComponent` metaclass with
``rl_alias='dp_distillation'``.
"""
from __future__ import annotations

import math
from typing import Any, ClassVar, Iterable, Mapping

from aqp_rl.core.reward import RewardTerm


class DPDistillation(RewardTerm):
    """KL-divergence penalty against a DP-oracle action distribution.

    Parameters
    ----------
    weight:
        Composite multiplier.
    ada:
        TradeMaster's ``ada`` coefficient. Larger ⇒ stronger pull to
        match the DP oracle. Default ``1.0``.
    eps:
        Numerical floor added to both distributions before the
        log-ratio. Default ``1e-8``.
    agent_dist_key:
        ``info`` key holding the agent's per-step softmax distribution.
        Default ``"agent_action_distribution"``.
    demo_key:
        ``info`` key holding the DP oracle distribution. Default
        ``"DP_action"`` (matches TradeMaster's env-level convention).
    """

    rl_alias: ClassVar[str] = "dp_distillation"
    rl_source: ClassVar[str] = "trademaster_hft"
    rl_category: ClassVar[str] = "shaping"
    rl_tags: ClassVar[tuple[str, ...]] = ("dp", "distillation", "hft", "kl")

    def __init__(
        self,
        *,
        weight: float = 1.0,
        ada: float = 1.0,
        eps: float = 1e-8,
        agent_dist_key: str = "agent_action_distribution",
        demo_key: str = "DP_action",
    ) -> None:
        if ada < 0:
            raise ValueError(f"DPDistillation ada must be ≥ 0; got {ada!r}")
        if eps <= 0:
            raise ValueError(f"DPDistillation eps must be > 0; got {eps!r}")
        super().__init__(name="dp_distillation", weight=weight)
        self.ada = float(ada)
        self.eps = float(eps)
        self.agent_dist_key = str(agent_dist_key)
        self.demo_key = str(demo_key)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        agent_dist = _to_distribution(info.get(self.agent_dist_key), eps=self.eps)
        demo = _to_distribution(info.get(self.demo_key), eps=self.eps)
        if agent_dist is None or demo is None:
            return 0.0
        if len(agent_dist) != len(demo):
            return 0.0
        kl = sum(
            p * math.log(p / q) for p, q in zip(agent_dist, demo, strict=False) if p > 0
        )
        # Reward is NEGATIVE of the KL (composite multiplies by positive
        # `weight` so the contribution is a penalty).
        return float(-self.ada * kl)

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out.update(
            {
                "ada": self.ada,
                "eps": self.eps,
                "agent_dist_key": self.agent_dist_key,
                "demo_key": self.demo_key,
            }
        )
        return out


def _to_distribution(value: Any, *, eps: float) -> list[float] | None:
    """Coerce an iterable into a normalised probability distribution.

    Returns ``None`` when the input is missing / unparseable / has zero
    mass. Otherwise returns a list summing to 1.0 with every entry ≥
    ``eps`` (re-normalised after the floor is applied).
    """
    if value is None:
        return None
    try:
        if hasattr(value, "tolist"):
            value = value.tolist()
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
            return None
        raw = [float(x) for x in value]
    except (TypeError, ValueError):
        return None
    if not raw:
        return None
    # Clip negatives (e.g. a logits vector slipped through) to zero,
    # add eps floor, renormalise.
    cleaned = [max(0.0, v) + eps for v in raw]
    total = sum(cleaned)
    if total <= 0:
        return None
    return [c / total for c in cleaned]


__all__ = ["DPDistillation"]
