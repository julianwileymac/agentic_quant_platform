"""Market impact + slippage models for the simulated brokerage.

Two models are provided out of the box:

- :class:`LinearBpsImpact` — the legacy fixed-bps slippage. Cheap,
  deterministic, but identical no matter how big the order is.
- :class:`SquareRootImpact` — a research-grade square-root model
  ``Δp / p = k · σ · sqrt(qty / ADV)``. Captures the empirically
  observed curvature: doubling order size doesn't double impact.

The :class:`SimulatedBrokerage` selects a model via a constructor
kwarg, defaulting to :class:`LinearBpsImpact` to preserve backward
compatibility. Strategies / engines that want realistic impact
(institutional sizing, large-cap research) plug in
:class:`SquareRootImpact` with their estimate of ``k`` (impact
coefficient) and ``sigma`` (return volatility) — both defaults are
sensible for US equities.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from aqp.core.types import OrderSide


class MarketImpactModel(ABC):
    """Returns the **fill price** given a base price + order details.

    The model is responsible for both directional (buy fills worse,
    sell fills worse) and size-dependent slippage.
    """

    name: str = "base"

    @abstractmethod
    def fill_price(
        self,
        *,
        base_price: float,
        side: OrderSide,
        quantity: float,
        adv: float | None = None,
    ) -> float:
        """Return the price at which the order should fill."""


@dataclass
class LinearBpsImpact(MarketImpactModel):
    """Fixed bps slippage applied symmetrically to buys and sells."""

    name: str = "linear_bps"
    bps: float = 2.0

    def fill_price(
        self,
        *,
        base_price: float,
        side: OrderSide,
        quantity: float,
        adv: float | None = None,
    ) -> float:
        slip = base_price * (self.bps / 10_000.0)
        return base_price + slip if side == OrderSide.BUY else base_price - slip


@dataclass
class SquareRootImpact(MarketImpactModel):
    """Square-root market impact: ``Δp / p = k * σ * sqrt(qty / ADV)``.

    Parameters:
        k: empirical impact coefficient. ``0.5`` is a commonly cited
           starting point for US large-cap equities; the literature
           ranges 0.3..1.0 depending on how one defines ADV.
        sigma: realised return volatility. Falls back to ``0.02``
            (2%) per bar when not provided, matching daily large-cap
            equity volatility.
        floor_bps: a hard floor on the bps slippage even for tiny
            orders, so the model still captures spread crossing.
        adv_default: fallback ADV (in shares / contracts) when the
            order doesn't supply one. ``1e6`` is reasonable for
            mid-cap US equities; tune per asset class.
    """

    name: str = "sqrt_impact"
    k: float = 0.5
    sigma: float = 0.02
    floor_bps: float = 1.0
    adv_default: float = 1_000_000.0

    def fill_price(
        self,
        *,
        base_price: float,
        side: OrderSide,
        quantity: float,
        adv: float | None = None,
    ) -> float:
        effective_adv = float(adv if adv and adv > 0 else self.adv_default)
        if effective_adv <= 0:
            ratio = 0.0
        else:
            ratio = math.sqrt(max(0.0, float(quantity)) / effective_adv)
        bps_from_impact = (self.k * self.sigma * ratio) * 10_000.0  # impact in bps
        bps = max(float(self.floor_bps), bps_from_impact)
        slip = base_price * (bps / 10_000.0)
        return base_price + slip if side == OrderSide.BUY else base_price - slip


def build_impact_model(spec: dict | None) -> MarketImpactModel:
    """Construct a :class:`MarketImpactModel` from a small spec dict.

    Examples::

        build_impact_model(None) -> LinearBpsImpact()
        build_impact_model({"kind": "sqrt", "k": 0.4, "sigma": 0.03})
        build_impact_model({"kind": "linear", "bps": 5.0})
    """
    if not spec:
        return LinearBpsImpact()
    kind = str(spec.get("kind") or "linear").lower()
    if kind in ("linear", "linear_bps", "bps"):
        return LinearBpsImpact(bps=float(spec.get("bps", 2.0)))
    if kind in ("sqrt", "sqrt_impact", "square_root"):
        return SquareRootImpact(
            k=float(spec.get("k", 0.5)),
            sigma=float(spec.get("sigma", 0.02)),
            floor_bps=float(spec.get("floor_bps", 1.0)),
            adv_default=float(spec.get("adv_default", 1_000_000.0)),
        )
    raise ValueError(f"unsupported market impact kind: {kind!r}")


__all__ = [
    "LinearBpsImpact",
    "MarketImpactModel",
    "SquareRootImpact",
    "build_impact_model",
]
