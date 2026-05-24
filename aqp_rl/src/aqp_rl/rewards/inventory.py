"""Cartea-Jaimungal full inventory reward — running + terminal penalty.

The Cartea-Jaimungal-Penalva canonical market-making / liquidation
reward (Ch. 8 + Ch. 10 of *Algorithmic and High-Frequency Trading*,
CUP 2015) is::

    r_t = ΔPnL_t − φ · I_t² · Δt − α · I_T² · 1{t = T}

Where:

- ``ΔPnL_t`` is the step's mark-to-market PnL change.
- ``φ`` is the running inventory-variance penalty per unit time.
- ``α`` is the terminal inventory penalty (encourages flat at horizon).
- ``I_t`` is the current inventory.
- ``Δt`` is the step duration in the canonical unit (defaults to 1).
- ``1{t = T}`` is the indicator function for the terminal step.

The existing
:class:`aqp_rl.rewards.inventory_quadratic.InventoryQuadraticPenaltyTerm`
covers only the running ``-φ · q²`` piece. This term ships the FULL
Cartea-Jaimungal reward including the terminal piece.

Reads ``info["inventory"]`` (or ``next_state["inventory"]``) for ``I_t``
and ``info["is_terminal"]`` (or :class:`gymnasium`'s ``terminated`` flag
in ``info["terminated"]``) to detect ``t = T``.

Hard rule 19: registered through :class:`RLComponent` metaclass with
``rl_alias='running_inventory'``.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

from aqp_rl.core.reward import RewardTerm


class RunningInventoryPenalty(RewardTerm):
    """Cartea-Jaimungal running + terminal inventory penalty.

    Parameters
    ----------
    weight:
        Composite multiplier.
    phi:
        Running inventory-variance penalty per unit time. Default ``1e-4``.
    alpha:
        Terminal inventory penalty. Default ``1e-3``. Higher = stronger
        push to flatten at horizon.
    dt:
        Step duration in the canonical unit. Default ``1.0`` (one
        bar per step).
    include_pnl:
        When ``True`` (default), the term contributes the step PnL
        change ``ΔPnL_t`` in addition to the penalties. When ``False``,
        only the penalties are emitted (caller is expected to compose
        with :class:`aqp_rl.rewards.pnl.PnLTerm` for the positive PnL
        piece).
    inventory_key:
        ``info`` key holding the current inventory ``I_t``. Default
        ``"inventory"``.
    """

    rl_alias: ClassVar[str] = "running_inventory"
    rl_source: ClassVar[str] = "cartea_jaimungal_2015"
    rl_category: ClassVar[str] = "constraint"
    rl_tags: ClassVar[tuple[str, ...]] = ("inventory", "cartea_jaimungal", "market_making")

    def __init__(
        self,
        *,
        weight: float = 1.0,
        phi: float = 1e-4,
        alpha: float = 1e-3,
        dt: float = 1.0,
        include_pnl: bool = True,
        inventory_key: str = "inventory",
    ) -> None:
        super().__init__(name="running_inventory", weight=weight)
        if phi < 0:
            raise ValueError(f"RunningInventoryPenalty phi must be ≥ 0; got {phi!r}")
        if alpha < 0:
            raise ValueError(f"RunningInventoryPenalty alpha must be ≥ 0; got {alpha!r}")
        if dt <= 0:
            raise ValueError(f"RunningInventoryPenalty dt must be > 0; got {dt!r}")
        self.phi = float(phi)
        self.alpha = float(alpha)
        self.dt = float(dt)
        self.include_pnl = bool(include_pnl)
        self.inventory_key = str(inventory_key)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        # Running penalty: −φ · I_t² · Δt
        inv = info.get(self.inventory_key)
        if inv is None:
            inv = next_state.get(self.inventory_key)
        try:
            i_t = float(inv) if inv is not None else 0.0
        except (TypeError, ValueError):
            i_t = 0.0
        running = -self.phi * i_t * i_t * self.dt

        # Terminal penalty: −α · I_T² · 1{t = T}
        is_terminal = bool(
            info.get("is_terminal") or info.get("terminated") or False
        )
        terminal = -self.alpha * i_t * i_t if is_terminal else 0.0

        # Optional PnL contribution: ΔPnL_t
        pnl_contribution = 0.0
        if self.include_pnl:
            prev_pv = float(state.get("portfolio_value", 0.0) or 0.0)
            curr_pv = float(next_state.get("portfolio_value", prev_pv) or prev_pv)
            pnl_contribution = curr_pv - prev_pv

        return float(pnl_contribution + running + terminal)

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out.update(
            {
                "phi": self.phi,
                "alpha": self.alpha,
                "dt": self.dt,
                "include_pnl": self.include_pnl,
                "inventory_key": self.inventory_key,
            }
        )
        return out


__all__ = ["RunningInventoryPenalty"]
