"""HFT / LOB strategy library.

Each strategy contains the *signal math* from the corresponding
hftbacktest example notebook. The engine integration is provided by
:class:`aqp.backtest.hft.LobBacktestEngine` (the in-process Numba+Rust
driver loop) so calling ``run()`` on any of these strategies now
materialises orders against a live order book.

Two of the strategies — :class:`GLFTMM` and :class:`AvellanedaStoikovMM`
— delegate the closed-form quote math to
:mod:`aqp.optimal_control.avellaneda_stoikov`. That keeps the per-bar
``on_event`` body pure-Python and import-cheap, while the JAX-compiled
helpers do the actual numeric work.
"""
from __future__ import annotations

import logging

from aqp.core.registry import register
from aqp.data.microstructure import depth_slope, microprice, order_book_imbalance
from aqp.optimal_control.avellaneda_stoikov import (
    AvellanedaStoikovParams,
    compute_optimal_quotes,
    glft_closed_form,
)
from aqp.strategies.lob import LobState, LobStrategy, OrderIntent

logger = logging.getLogger(__name__)


@register("GLFTMM", source="hftbacktest", category="market_making")
class GLFTMM(LobStrategy):
    """Guéant-Lehalle-Fernandez-Tapia closed-form market making.

    Quotes are computed by
    :func:`aqp.optimal_control.avellaneda_stoikov.glft_closed_form`,
    which encodes the steady-state Avellaneda-Stoikov approximation
    derived in Guéant et al. 2013 eq. (4.3).
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
        result = glft_closed_form(
            mid_price=state.mid_price,
            inventory=state.position,
            gamma=self.gamma,
            sigma=self.sigma,
            kappa=self.kappa,
        )
        intents: list[OrderIntent] = []
        if state.position < self.max_position:
            intents.append(
                OrderIntent(
                    side="buy",
                    price=result.bid,
                    quantity=self.order_size,
                    post_only=True,
                    tag="glft_bid",
                )
            )
        if state.position > -self.max_position:
            intents.append(
                OrderIntent(
                    side="sell",
                    price=result.ask,
                    quantity=self.order_size,
                    post_only=True,
                    tag="glft_ask",
                )
            )
        return intents


@register("AvellanedaStoikovMM", source="aqp", category="market_making")
class AvellanedaStoikovMM(LobStrategy):
    """Full finite-horizon Avellaneda-Stoikov market making.

    Differs from :class:`GLFTMM` by tracking an explicit horizon
    ``T_minus_t`` that decays each ``on_event`` call. Quotes widen
    near terminal close to encourage inventory unwind. Uses the
    JAX-compiled solver from
    :func:`aqp.optimal_control.avellaneda_stoikov.compute_optimal_quotes`.
    """

    strategy_id = "avellaneda_stoikov_mm"

    def __init__(
        self,
        gamma: float = 0.1,
        sigma: float = 0.01,
        k: float = 1.5,
        order_size: float = 1.0,
        max_position: float = 10.0,
        horizon: float = 1.0,
    ) -> None:
        self.params = AvellanedaStoikovParams(
            gamma=gamma, sigma=sigma, k=k, T_minus_t=horizon
        )
        self.order_size = order_size
        self.max_position = max_position
        self._initial_horizon = horizon
        self._t_minus_t = horizon

    def on_event(self, state: LobState) -> list[OrderIntent]:
        result = compute_optimal_quotes(
            mid_price=state.mid_price,
            inventory=state.position,
            gamma=self.params.gamma,
            sigma=self.params.sigma,
            k=self.params.k,
            T_minus_t=max(self._t_minus_t, 1e-6),
        )
        # Decay horizon by ~1/2000 of the initial horizon per event so a
        # day's worth of ticks roughly traverses [horizon, 0]. The runner
        # can override by writing directly to ``self._t_minus_t``.
        self._t_minus_t = max(
            self._t_minus_t - self._initial_horizon / 2000.0, 1e-6
        )
        intents: list[OrderIntent] = []
        if state.position < self.max_position:
            intents.append(
                OrderIntent(
                    side="buy",
                    price=result.bid,
                    quantity=self.order_size,
                    post_only=True,
                    tag="avst_bid",
                )
            )
        if state.position > -self.max_position:
            intents.append(
                OrderIntent(
                    side="sell",
                    price=result.ask,
                    quantity=self.order_size,
                    post_only=True,
                    tag="avst_ask",
                )
            )
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
