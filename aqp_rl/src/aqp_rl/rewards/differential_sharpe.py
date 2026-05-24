"""Differential Sharpe Ratio — Moody & Saffell 1998 step-wise recurrence.

The canonical reference: J. Moody and M. Saffell, "Reinforcement Learning
for Trading", *Advances in Neural Information Processing Systems* 11
(NIPS 1998); extended in J. Moody and M. Saffell, "Learning to Trade via
Direct Reinforcement", *IEEE Transactions on Neural Networks* 12 (4),
875-889 (2001).

The DSR isolates the *marginal* contribution of the current step's
return to the moving Sharpe ratio. Unlike :class:`aqp_rl.rewards.risk.SharpeTerm`
(which computes a rolling Sharpe over an in-episode window) the DSR is
a true per-step reward — it requires no warm-up and can drive
online policy-gradient updates without aliasing.

The math (verbatim from §4 of Moody & Saffell 1998)::

    Updates per step::

        ΔA_t = R_t − A_{t-1}
        ΔB_t = R_t² − B_{t-1}
        A_t  = A_{t-1} + η · ΔA_t          # EMA of returns
        B_t  = B_{t-1} + η · ΔB_t          # EMA of squared returns

    Sharpe correction constant (Moody & Saffell eq. 13)::

        K_η = sqrt((1 − η/2) / (1 − η))

    Sharpe ratio at step t::

        S_t = A_t / (K_η · sqrt(B_t − A_t²))

    Per-step differential contribution (Moody & Saffell eq. 16)::

        D_t = (B_{t-1} · ΔA_t − ½ · A_{t-1} · ΔB_t) / (B_{t-1} − A_{t-1}²)^{3/2}

The DSR's denominator can blow up when ``B - A²`` is small (the agent
has very little variance in its returns). We guard with a configurable
``eps`` floor: when the denominator falls below ``eps`` we emit zero
for that step (and still update the EMAs so the warm-up completes).

Hard rule 19: registered through the :class:`RLComponent` metaclass
with ``rl_alias='differential_sharpe'``. No manual ``@register``.
"""
from __future__ import annotations

import math
from typing import Any, ClassVar, Mapping

from aqp_rl.core.reward import RewardTerm


class DifferentialSharpe(RewardTerm):
    """Differential Sharpe Ratio per-step reward (Moody & Saffell 1998).

    The recurrence is stateful — every call to :meth:`compute` updates
    the EMAs ``A_t`` and ``B_t``. The reward returned at step ``t`` is
    the per-step contribution ``D_t`` to the running Sharpe ratio.

    Parameters
    ----------
    eta:
        EMA adaptation rate. ``η ∈ (0, 1)``. Smaller values produce a
        slower-moving Sharpe baseline (less noisy reward, slower
        adaptation to regime changes). Default ``1e-2`` matches the
        Moody & Saffell trading experiments.
    weight:
        Composite multiplier (forwarded to :class:`RewardTerm`).
    warmup:
        Steps before any non-zero reward is emitted. Allows the EMAs
        to build a baseline so the first few ``D_t`` aren't dominated
        by the initialisation artefact. Default ``1``.
    eps:
        Numerical floor below which the denominator
        ``(B_{t-1} − A_{t-1}²)^{3/2}`` is treated as zero. Default
        ``1e-12``.
    return_key:
        ``info`` key the term reads the per-step return ``R_t`` from.
        Default ``"portfolio_return"``. Falls back to computing it from
        ``state['portfolio_value']`` → ``next_state['portfolio_value']``
        when the key is absent.
    """

    rl_alias: ClassVar[str] = "differential_sharpe"
    rl_source: ClassVar[str] = "moody_saffell_1998"
    rl_category: ClassVar[str] = "risk"
    rl_tags: ClassVar[tuple[str, ...]] = ("dsr", "differential", "online-sharpe")

    def __init__(
        self,
        *,
        eta: float = 1e-2,
        weight: float = 1.0,
        warmup: int = 1,
        eps: float = 1e-12,
        return_key: str = "portfolio_return",
    ) -> None:
        if not 0.0 < eta < 1.0:
            raise ValueError(f"DifferentialSharpe eta must be in (0, 1); got {eta!r}")
        super().__init__(name="differential_sharpe", weight=weight)
        self.eta = float(eta)
        self.warmup = int(warmup)
        self.eps = float(eps)
        self.return_key = str(return_key)
        # K_η correction (Moody & Saffell eq. 13). Pre-computed once.
        self._k_eta = math.sqrt((1.0 - eta / 2.0) / (1.0 - eta))
        self._A = 0.0
        self._B = 0.0
        self._t = 0

    @property
    def K_eta(self) -> float:
        """Moody & Saffell ``K_η`` correction constant.

        Exposed so callers can inspect the per-step Sharpe denominator
        without re-deriving the formula from ``eta``.
        """
        return self._k_eta

    def reset(self) -> None:
        """Reset the EMAs at episode boundary."""
        self._A = 0.0
        self._B = 0.0
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
        b_prev = self._B
        delta_a = ret - a_prev
        delta_b = ret * ret - b_prev

        # Always update the EMAs so the warm-up bookkeeping converges.
        self._A = a_prev + self.eta * delta_a
        self._B = b_prev + self.eta * delta_b
        self._t += 1

        if self._t <= self.warmup:
            return 0.0

        denom_sq = b_prev - a_prev * a_prev
        if denom_sq <= self.eps:
            return 0.0
        denom = denom_sq ** 1.5
        d_t = (b_prev * delta_a - 0.5 * a_prev * delta_b) / denom
        # The (1/K_η) factor cancels out for the *differential* — we
        # only apply it to the absolute Sharpe estimate.
        return float(d_t)

    def current_sharpe(self) -> float:
        """Return the *running* (not differential) Sharpe estimate.

        Useful for diagnostics / dashboards that want to plot the
        absolute Sharpe alongside the per-step DSR contribution.
        Returns ``0.0`` until enough EMA mass has accumulated.
        """
        if self._t <= self.warmup:
            return 0.0
        var = self._B - self._A * self._A
        if var <= self.eps:
            return 0.0
        return float(self._A / (self._k_eta * math.sqrt(var)))

    def _extract_return(
        self,
        state: Mapping[str, Any],
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        """Resolve the per-step return ``R_t`` from info / state / next_state."""
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
                "return_key": self.return_key,
                "K_eta": self._k_eta,
            }
        )
        return out


__all__ = ["DifferentialSharpe"]
