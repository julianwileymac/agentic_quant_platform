"""Hindsight reward — DeepScalper (Sun et al. CIKM 2022).

DeepScalper trains a DQN over a discrete volume action by augmenting
the immediate reward with a *forward-looking* term that the env can
materialise because the historical dataset is fully known at training
time. The reward shape is::

    reward_t = compound · ((p_{t+1} − p_t) + λ · (p_{t+k} − p_t))

Where:

- ``compound`` is the agent's signed position (positive = long).
- ``p_t`` is the current price; ``p_{t+1}`` is the next-step price
  (immediate PnL term).
- ``p_{t+k}`` is the price ``k`` bars ahead — the "hindsight" lookahead.
- ``λ`` (``future_weights``) controls how much weight the agent
  places on the future PnL relative to the immediate PnL.

The pattern produces stronger intraday momentum capture because the
agent learns to ride trends past the next bar. At inference time the
agent only sees ``p_t`` so the hindsight reward is training-only
auxiliary signal — exactly mirroring DeepScalper's "future-aware
auxiliary loss" formulation.

The env is expected to stamp into ``info`` (per step):

- ``position`` (signed) — the agent's compound position.
- ``current_price`` — the price at step ``t``.
- ``next_price`` — the price at step ``t+1``.
- ``future_price`` — the price at step ``t+k`` (the hindsight horizon).

When ``future_price`` is absent (live trading) the term degrades to
the immediate-PnL piece only.

Hard rule 19: registered through :class:`RLComponent` metaclass with
``rl_alias='hindsight'``.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

from aqp_rl.core.reward import RewardTerm


class HindsightReward(RewardTerm):
    """DeepScalper hindsight reward with optional forward lookahead.

    Parameters
    ----------
    weight:
        Composite multiplier.
    future_weight:
        ``λ`` multiplier on the hindsight PnL contribution. Default
        ``0.2`` matching the DeepScalper paper.
    position_key, current_price_key, next_price_key, future_price_key:
        ``info`` keys the env stamps. Override only when porting an
        existing env that uses different naming.
    """

    rl_alias: ClassVar[str] = "hindsight"
    rl_source: ClassVar[str] = "deepscalper_2022"
    rl_category: ClassVar[str] = "pnl"
    rl_tags: ClassVar[tuple[str, ...]] = ("hindsight", "deepscalper", "lookahead")

    def __init__(
        self,
        *,
        weight: float = 1.0,
        future_weight: float = 0.2,
        position_key: str = "position",
        current_price_key: str = "current_price",
        next_price_key: str = "next_price",
        future_price_key: str = "future_price",
    ) -> None:
        if future_weight < 0:
            raise ValueError(
                f"HindsightReward future_weight must be ≥ 0; got {future_weight!r}"
            )
        super().__init__(name="hindsight", weight=weight)
        self.future_weight = float(future_weight)
        self.position_key = str(position_key)
        self.current_price_key = str(current_price_key)
        self.next_price_key = str(next_price_key)
        self.future_price_key = str(future_price_key)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        position = _safe_float(info.get(self.position_key))
        if position == 0.0:
            return 0.0
        p_now = _safe_float(info.get(self.current_price_key), default=None)
        p_next = _safe_float(info.get(self.next_price_key), default=None)
        if p_now is None or p_next is None:
            return 0.0
        immediate = p_next - p_now

        p_future = info.get(self.future_price_key)
        if p_future is None or self.future_weight == 0.0:
            return float(position * immediate)
        future_val = _safe_float(p_future, default=None)
        if future_val is None:
            return float(position * immediate)
        hindsight = future_val - p_now
        return float(position * (immediate + self.future_weight * hindsight))

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out.update(
            {
                "future_weight": self.future_weight,
                "position_key": self.position_key,
                "current_price_key": self.current_price_key,
                "next_price_key": self.next_price_key,
                "future_price_key": self.future_price_key,
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


__all__ = ["HindsightReward"]
