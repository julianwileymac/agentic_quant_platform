"""Microprice directional alpha (Stoikov 2018).

Uses the volume-weighted microprice as a fair-value estimator. The
microprice converges to the side with deeper queue and is a robust
short-term forecast of the next traded price. When the microprice
deviates from the midprice by more than ``threshold_bps``, the
strategy fires a market order in the deviation direction.

See :func:`aqp.data.microstructure.microprice` and Stoikov (2018,
"The Microprice"). Companion to
:class:`aqp.strategies.hft.obi_directional.OBIDirectionalAlpha` —
microprice is just the variance-minimising linear combination of mid
and OBI, so these two strategies pair naturally as an ensemble.
"""
from __future__ import annotations

import logging

from aqp.core.registry import register
from aqp.data.microstructure import microprice
from aqp.strategies.lob import LobState, LobStrategy, OrderIntent

logger = logging.getLogger(__name__)


@register("MicropriceAlpha", source="research_report_2026", category="microstructure")
class MicropriceAlpha(LobStrategy):
    """Microprice-vs-midprice deviation alpha.

    Parameters
    ----------
    threshold_bps
        Minimum microprice deviation from mid (basis points) to fire.
    order_size
        Quantity per market order.
    max_position
        Inventory cap; the strategy refuses to add when at cap.
    cooldown_events
        Minimum events between trades to avoid rapid-fire whipsaws.
    """

    strategy_id = "microprice_alpha"

    def __init__(
        self,
        threshold_bps: float = 1.5,
        order_size: float = 1.0,
        max_position: float = 10.0,
        cooldown_events: int = 50,
    ) -> None:
        self.threshold_bps = float(threshold_bps)
        self.order_size = float(order_size)
        self.max_position = float(max_position)
        self.cooldown_events = int(cooldown_events)
        self._events_since_trade = 0

    def on_event(self, state: LobState) -> list[OrderIntent]:
        self._events_since_trade += 1
        if state.best_bid <= 0 or state.best_ask <= 0:
            return []
        mp = float(
            microprice(state.best_bid, state.best_ask, state.bid_qty, state.ask_qty)
        )
        mid = state.mid_price
        if mid <= 0:
            return []
        edge_bps = (mp - mid) / mid * 1e4

        if self._events_since_trade < self.cooldown_events:
            return []

        intents: list[OrderIntent] = []
        if edge_bps >= self.threshold_bps and state.position < self.max_position:
            intents.append(
                OrderIntent(
                    side="buy",
                    price=state.best_ask,
                    quantity=self.order_size,
                    order_type="market",
                    time_in_force="ioc",
                    post_only=False,
                    tag="microprice_long",
                )
            )
            self._events_since_trade = 0
        elif edge_bps <= -self.threshold_bps and state.position > -self.max_position:
            intents.append(
                OrderIntent(
                    side="sell",
                    price=state.best_bid,
                    quantity=self.order_size,
                    order_type="market",
                    time_in_force="ioc",
                    post_only=False,
                    tag="microprice_short",
                )
            )
            self._events_since_trade = 0
        return intents
