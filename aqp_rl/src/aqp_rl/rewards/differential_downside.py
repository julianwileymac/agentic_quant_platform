"""Differential Downside Deviation Ratio (D3R) — Sortino's step-wise sibling.

The Differential Sharpe Ratio
(:class:`aqp_rl.rewards.differential_sharpe.DifferentialSharpe`) penalises
*all* variance — positive and negative — symmetrically. For trading
applications where upside variance is exactly what we want to capture,
substituting a downside-only second moment yields the Differential
Downside Deviation Ratio (D3R), a step-wise analogue of the Sortino
ratio.

Derivation (Moody & Saffell 1998 style)::

    Updates per step::

        ΔA_t  = R_t − A_{t-1}
        ΔDD_t = min(R_t, 0)² − DD_{t-1}
        A_t   = A_{t-1} + η · ΔA_t        # EMA of returns
        DD_t  = DD_{t-1} + η · ΔDD_t      # EMA of downside variance

    Per-step differential::

        D^{D3R}_t = (DD_{t-1} · ΔA_t − ½ · A_{t-1} · ΔDD_t) / (DD_{t-1})^{3/2}

    Sortino-style running estimate (eq. analogue)::

        S^D_t = A_t / sqrt(DD_t)

Empirical work (Almahdi & Yang 2017; Moody & Saffell 2001) shows that
D3R-trained traders take more neutral positions in turbulent regimes
and produce significantly higher Sterling ratios (return / max
drawdown) than DSR-trained baselines.

Hard rule 19: registered through :class:`RLComponent` metaclass with
``rl_alias='differential_downside'``.
"""
from __future__ import annotations

import math
from typing import Any, ClassVar, Mapping

from aqp_rl.core.reward import RewardTerm


class DifferentialDownside(RewardTerm):
    """Differential Downside Deviation Ratio per-step reward.

    Parameters mirror :class:`DifferentialSharpe`; the only change is
    that the second-moment EMA accumulates ``min(R_t, 0)²`` instead of
    ``R_t²``.

    Parameters
    ----------
    eta:
        EMA adaptation rate. ``η ∈ (0, 1)``.
    weight:
        Composite multiplier.
    warmup:
        Steps before non-zero rewards. Default ``1``.
    eps:
        Floor below which the denominator ``DD_{t-1}^{3/2}`` is treated
        as zero (no downside variance yet ⇒ zero reward).
    target_return:
        Minimum acceptable return ``MAR``. ``R_t < target_return`` is
        treated as downside. Default ``0.0`` (the canonical Sortino).
    return_key:
        ``info`` key the term reads ``R_t`` from. Default
        ``"portfolio_return"``.
    """

    rl_alias: ClassVar[str] = "differential_downside"
    rl_source: ClassVar[str] = "moody_saffell_1998"
    rl_category: ClassVar[str] = "risk"
    rl_tags: ClassVar[tuple[str, ...]] = ("d3r", "differential", "online-sortino")

    def __init__(
        self,
        *,
        eta: float = 1e-2,
        weight: float = 1.0,
        warmup: int = 1,
        eps: float = 1e-12,
        target_return: float = 0.0,
        return_key: str = "portfolio_return",
    ) -> None:
        if not 0.0 < eta < 1.0:
            raise ValueError(f"DifferentialDownside eta must be in (0, 1); got {eta!r}")
        super().__init__(name="differential_downside", weight=weight)
        self.eta = float(eta)
        self.warmup = int(warmup)
        self.eps = float(eps)
        self.target_return = float(target_return)
        self.return_key = str(return_key)
        self._A = 0.0
        self._DD = 0.0
        self._t = 0

    def reset(self) -> None:
        self._A = 0.0
        self._DD = 0.0
        self._t = 0

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        ret = self._extract_return(state, next_state, info)
        a_prev = self._A
        dd_prev = self._DD
        delta_a = ret - a_prev
        downside_sq = (ret - self.target_return) ** 2 if ret < self.target_return else 0.0
        delta_dd = downside_sq - dd_prev

        self._A = a_prev + self.eta * delta_a
        self._DD = dd_prev + self.eta * delta_dd
        self._t += 1

        if self._t <= self.warmup or dd_prev <= self.eps:
            return 0.0

        denom = dd_prev ** 1.5
        d3r = (dd_prev * delta_a - 0.5 * a_prev * delta_dd) / denom
        return float(d3r)

    def current_sortino(self) -> float:
        """Return the running Sortino estimate ``A_t / sqrt(DD_t)``.

        Returns ``0.0`` until enough downside variance has accumulated
        (no downside ⇒ denominator unstable ⇒ surface as zero rather
        than ``+∞``).
        """
        if self._t <= self.warmup or self._DD <= self.eps:
            return 0.0
        return float(self._A / math.sqrt(self._DD))

    def _extract_return(
        self,
        state: Mapping[str, Any],
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        if info and self.return_key in info:
            try:
                return float(info[self.return_key])
            except (TypeError, ValueError):
                pass
        prev_pv = float(state.get("portfolio_value", 0.0) or 0.0)
        curr_pv = float(next_state.get("portfolio_value", prev_pv) or prev_pv)
        if prev_pv <= 0:
            return 0.0
        return (curr_pv - prev_pv) / prev_pv

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out.update(
            {
                "eta": self.eta,
                "warmup": self.warmup,
                "eps": self.eps,
                "target_return": self.target_return,
                "return_key": self.return_key,
            }
        )
        return out


__all__ = ["DifferentialDownside"]
