"""Implementation-shortfall reward for optimal-execution agents.

Implementation Shortfall (IS) measures the dollar cost of executing a
block order relative to the arrival mid-price. Lower IS = cheaper
execution. Per Almgren & Chriss 2001 and the FinRL-X execution
blueprint, the per-step reward for an optimal-execution agent is::

    IS_step = q_k · (P_arrival − P_fill,k)
    var_step = λ · Var(P_fill,k)
    reward_t = −(IS_step + var_step) / Q

Where:

- ``q_k`` is the number of shares executed in step ``k``.
- ``P_arrival`` is the mid-price at the agent's first decision.
- ``P_fill,k`` is the volume-weighted attained price for step ``k``.
- ``Q`` is the total block size (normalises the reward so different
  block sizes are comparable).
- ``λ`` is a risk-aversion coefficient that penalises fill-price
  variance (mirrors the running variance term in the AC HJB).

The term reads its inputs from ``info`` (the env stamps
``arrival_price``, ``fill_price``, ``executed_shares`` and optionally
``fill_price_variance`` each step). Missing inputs ⇒ zero reward
(no execution this step).

Hard rule 19: registered through :class:`RLComponent` metaclass with
``rl_alias='implementation_shortfall'``.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

from aqp_rl.core.reward import RewardTerm


class ImplementationShortfall(RewardTerm):
    """Per-step implementation-shortfall reward.

    Parameters
    ----------
    weight:
        Composite multiplier.
    lambda_risk:
        Risk-aversion coefficient ``λ`` multiplying the per-step fill-price
        variance penalty. Default ``0.0`` (pure shortfall, no variance
        penalty). Maps directly onto Almgren-Chriss ``λ``.
    total_shares_key:
        ``info`` key holding the total block size ``Q``. The reward is
        normalised by ``Q`` so different block sizes are commensurate.
        When ``Q`` is missing the term falls back to the per-step raw
        shortfall (no normalisation).
    arrival_price_key:
        ``info`` key holding the arrival mid-price ``P_arrival``.
    fill_price_key:
        ``info`` key holding the volume-weighted fill price for the
        current step.
    executed_shares_key:
        ``info`` key holding the number of shares executed in the
        current step ``q_k``.
    fill_variance_key:
        ``info`` key holding the per-step fill-price variance (used
        only when ``lambda_risk > 0``).
    """

    rl_alias: ClassVar[str] = "implementation_shortfall"
    rl_source: ClassVar[str] = "almgren_chriss_2001"
    rl_category: ClassVar[str] = "execution"
    rl_tags: ClassVar[tuple[str, ...]] = ("execution", "implementation_shortfall", "is")

    def __init__(
        self,
        *,
        weight: float = 1.0,
        lambda_risk: float = 0.0,
        total_shares_key: str = "total_shares",
        arrival_price_key: str = "arrival_price",
        fill_price_key: str = "fill_price",
        executed_shares_key: str = "executed_shares",
        fill_variance_key: str = "fill_price_variance",
    ) -> None:
        super().__init__(name="implementation_shortfall", weight=weight)
        if lambda_risk < 0:
            raise ValueError(
                f"ImplementationShortfall lambda_risk must be ≥ 0; got {lambda_risk!r}"
            )
        self.lambda_risk = float(lambda_risk)
        self.total_shares_key = str(total_shares_key)
        self.arrival_price_key = str(arrival_price_key)
        self.fill_price_key = str(fill_price_key)
        self.executed_shares_key = str(executed_shares_key)
        self.fill_variance_key = str(fill_variance_key)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        q_k = _safe_float(info.get(self.executed_shares_key))
        if q_k == 0.0:
            return 0.0
        arrival = _safe_float(info.get(self.arrival_price_key), default=None)
        fill = _safe_float(info.get(self.fill_price_key), default=None)
        if arrival is None or fill is None:
            return 0.0

        is_step = q_k * (arrival - fill)
        var_step = 0.0
        if self.lambda_risk > 0:
            var = _safe_float(info.get(self.fill_variance_key))
            var_step = self.lambda_risk * var

        total = _safe_float(info.get(self.total_shares_key))
        denominator = total if total > 0 else 1.0
        # Negative sign: larger shortfall ⇒ more negative reward.
        return float(-(is_step + var_step) / denominator)

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out.update(
            {
                "lambda_risk": self.lambda_risk,
                "total_shares_key": self.total_shares_key,
                "arrival_price_key": self.arrival_price_key,
                "fill_price_key": self.fill_price_key,
                "executed_shares_key": self.executed_shares_key,
                "fill_variance_key": self.fill_variance_key,
            }
        )
        return out


def _safe_float(value: Any, default: float | None = 0.0) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = ["ImplementationShortfall"]
