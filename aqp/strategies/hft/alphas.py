"""HFT/LOB strategy stubs.

Each strategy contains the *signal math* from the corresponding
hftbacktest example notebook, but the engine plumbing (order
submission, queue model, latency simulation) is deferred to the future
LOB adapter described in
``extractions/_FUTURE_PROMPTS/lob_adapter_prompt.md``.
"""
from __future__ import annotations

import logging
import math

from aqp.core.registry import register
from aqp.data.microstructure import depth_slope, microprice, order_book_imbalance
from aqp.strategies.lob import LobState, LobStrategy, OrderIntent

logger = logging.getLogger(__name__)


@register("GLFTMM", source="hftbacktest", category="market_making")
class GLFTMM(LobStrategy):
    """Gueant-Lehalle-Fernandez-Tapia closed-form market making.

    Reservation price = mid - q * gamma * sigma^2 * (T - t).
    Optimal half-spread = gamma * sigma^2 * (T - t) + (2/gamma) * ln(1 + gamma/k).
    """

    strategy_id = "glft_mm"

    def __init__(
        self,
        gamma: float = 0.1,
        sigma: float = 0.01,
        kappa: float = 1.5,
        order_size: float = 1.0,
        max_position: float = 10.0,
    ) -> None:
        self.gamma = gamma
        self.sigma = sigma
        self.kappa = kappa
        self.order_size = order_size
        self.max_position = max_position

    def on_event(self, state: LobState) -> list[OrderIntent]:
        mid = state.mid_price
        q = state.position
        # reservation price (T - t taken as 1 in steady state)
        reservation = mid - q * self.gamma * (self.sigma ** 2)
        half_spread = self.gamma * (self.sigma ** 2) + (2.0 / self.gamma) * math.log(1 + self.gamma / self.kappa)
        bid_price = reservation - half_spread
        ask_price = reservation + half_spread
        intents: list[OrderIntent] = []
        if state.position < self.max_position:
            intents.append(OrderIntent(side="buy", price=bid_price, quantity=self.order_size, post_only=True, tag="glft_bid"))
        if state.position > -self.max_position:
            intents.append(OrderIntent(side="sell", price=ask_price, quantity=self.order_size, post_only=True, tag="glft_ask"))
        return intents


@register("GridMM", source="hftbacktest", category="market_making")
class GridMM(LobStrategy):
    """Symmetric grid quoting around mid."""

    strategy_id = "grid_mm"

    def __init__(self, grid_step: float = 0.5, n_levels: int = 5, order_size: float = 1.0) -> None:
        self.grid_step = grid_step
        self.n_levels = n_levels
        self.order_size = order_size

    def on_event(self, state: LobState) -> list[OrderIntent]:
        mid = state.mid_price
        intents: list[OrderIntent] = []
        for i in range(1, self.n_levels + 1):
            intents.append(OrderIntent(side="buy", price=mid - i * self.grid_step, quantity=self.order_size, tag=f"grid_b_{i}"))
            intents.append(OrderIntent(side="sell", price=mid + i * self.grid_step, quantity=self.order_size, tag=f"grid_a_{i}"))
        return intents


@register("ImbalanceAlphaMM", source="hftbacktest", category="market_making")
class ImbalanceAlphaMM(LobStrategy):
    """Skew quotes based on order book imbalance."""

    strategy_id = "imbalance_alpha_mm"

    def __init__(self, skew_strength: float = 1.0, base_half_spread: float = 0.5, order_size: float = 1.0) -> None:
        self.skew_strength = skew_strength
        self.base_half_spread = base_half_spread
        self.order_size = order_size

    def on_event(self, state: LobState) -> list[OrderIntent]:
        obi = order_book_imbalance(state.bid_qty, state.ask_qty)
        mid = state.mid_price
        skew = self.skew_strength * obi * self.base_half_spread
        bid_price = mid - self.base_half_spread + skew
        ask_price = mid + self.base_half_spread + skew
        return [
            OrderIntent(side="buy", price=bid_price, quantity=self.order_size, tag="imbalance_b"),
            OrderIntent(side="sell", price=ask_price, quantity=self.order_size, tag="imbalance_a"),
        ]


@register("BasisAlphaMM", source="hftbacktest", category="market_making")
class BasisAlphaMM(LobStrategy):
    """Cross-instrument basis as fair-value alpha.

    Reads ``state.extras["fair_value"]`` set by the engine from the
    related instrument; uses it as the centring point for quotes.
    """

    strategy_id = "basis_alpha_mm"

    def __init__(self, half_spread: float = 0.5, order_size: float = 1.0) -> None:
        self.half_spread = half_spread
        self.order_size = order_size

    def on_event(self, state: LobState) -> list[OrderIntent]:
        fair_value = state.extras.get("fair_value", state.mid_price)
        return [
            OrderIntent(side="buy", price=fair_value - self.half_spread, quantity=self.order_size, tag="basis_b"),
            OrderIntent(side="sell", price=fair_value + self.half_spread, quantity=self.order_size, tag="basis_a"),
        ]


@register("QueueAwareMM", source="hftbacktest", category="market_making")
class QueueAwareMM(LobStrategy):
    """Queue-position-aware market making for large-tick assets.

    Uses microprice as the centring point and depth slope to widen
    quotes when the book becomes shallow.
    """

    strategy_id = "queue_aware_mm"

    def __init__(self, base_half_spread: float = 0.5, slope_sensitivity: float = 0.001, order_size: float = 1.0) -> None:
        self.base_half_spread = base_half_spread
        self.slope_sensitivity = slope_sensitivity
        self.order_size = order_size

    def on_event(self, state: LobState) -> list[OrderIntent]:
        center = microprice(state.best_bid, state.best_ask, state.bid_qty, state.ask_qty)
        # widen when book is thin
        slope = 0.0
        if state.bid_prices is not None and state.bid_qtys is not None:
            slope = depth_slope(state.bid_prices, state.bid_qtys, state.mid_price)
        widen = self.slope_sensitivity / max(abs(slope), 1e-9)
        half = self.base_half_spread + min(widen, 5 * self.base_half_spread)
        return [
            OrderIntent(side="buy", price=center - half, quantity=self.order_size, tag="queue_b"),
            OrderIntent(side="sell", price=center + half, quantity=self.order_size, tag="queue_a"),
        ]
