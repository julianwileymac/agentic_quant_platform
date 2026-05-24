"""Smart Order Router.

A SOR takes a parent :class:`NewOrder` and decides:

1. Which venue(s) to route to.
2. How to split the quantity across venues.

The default :class:`LatencyAwareSOR` considers four factors per venue:
**price**, **latency**, **fee**, **fill probability**. Concrete
strategies override the weighting per asset class — equities care
mostly about price/fee, HFT cares mostly about latency, MEV bots care
exclusively about block inclusion probability.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

from aqp_bots.schemas.trading import NewOrder

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class VenueScore:
    """Score for one venue at one point in time."""

    venue: str
    price: Decimal
    latency_us: float
    fee_bps: float = 0.0
    fill_probability: float = 1.0
    raw: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class RoutedChild:
    """One outbound child slice the SOR has decided to send."""

    venue: str
    quantity: Decimal


class SmartOrderRouter(ABC):
    """Pluggable router base.

    Subclasses register through ``@register("name", kind="smart_order_router")``;
    the kernel resolves the chosen router via the AQP core registry per
    :attr:`ExecutionLayerSpec.smart_order_router`.
    """

    name: str = "base"

    @abstractmethod
    def route(
        self, parent: NewOrder, candidates: Iterable[VenueScore]
    ) -> list[RoutedChild]:
        ...


class LatencyAwareSOR(SmartOrderRouter):
    """Default SOR — minimizes expected cost = price + slippage + fee.

    Cost model:
        expected_cost = price + (latency_us * 1e-6 * impact_per_sec) + (fee_bps/1e4 * price)

    The single best venue receives the entire quantity; advanced multi-venue
    splitting requires :class:`MultiVenueSOR` (Phase 8 stretch goal).
    """

    name = "latency_aware"

    def __init__(
        self,
        *,
        impact_per_sec: float = 1e-3,
        price_weight: float = 1.0,
        latency_weight: float = 0.5,
        fee_weight: float = 1.0,
        fill_weight: float = 1.0,
    ) -> None:
        self.impact_per_sec = impact_per_sec
        self.price_weight = price_weight
        self.latency_weight = latency_weight
        self.fee_weight = fee_weight
        self.fill_weight = fill_weight

    def route(
        self, parent: NewOrder, candidates: Iterable[VenueScore]
    ) -> list[RoutedChild]:
        best: VenueScore | None = None
        best_score = float("inf")
        for c in candidates:
            score = self._score(parent, c)
            if score < best_score:
                best_score = score
                best = c
        if best is None:
            return []
        return [RoutedChild(venue=best.venue, quantity=parent.quantity)]

    def _score(self, parent: NewOrder, c: VenueScore) -> float:
        latency_cost = self.latency_weight * c.latency_us * self.impact_per_sec * 1e-6
        fee_cost = self.fee_weight * (c.fee_bps / 1e4) * float(c.price)
        price_term = self.price_weight * float(c.price)
        if parent.side.value == "buy":
            base = price_term + fee_cost + latency_cost
        else:
            base = -price_term + fee_cost + latency_cost
        # Penalise low fill probability.
        if c.fill_probability < 1.0:
            base += self.fill_weight * (1.0 - c.fill_probability) * float(c.price)
        return base


class RoundRobinSOR(SmartOrderRouter):
    """Trivial round-robin SOR — for testing.

    Splits ``parent.quantity`` equally across the candidate venues.
    """

    name = "round_robin"

    def route(
        self, parent: NewOrder, candidates: Iterable[VenueScore]
    ) -> list[RoutedChild]:
        cand_list = list(candidates)
        if not cand_list:
            return []
        slice_qty = parent.quantity / Decimal(len(cand_list))
        return [RoutedChild(venue=c.venue, quantity=slice_qty) for c in cand_list]


__all__ = [
    "LatencyAwareSOR",
    "RoundRobinSOR",
    "RoutedChild",
    "SmartOrderRouter",
    "VenueScore",
]
