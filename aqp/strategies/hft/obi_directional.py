"""Order-book-imbalance directional alpha (Stanford HFT 2016).

Implements the directional OBI signal from
``MS&E 448 — A Survey of High-Frequency Trading Strategies`` (Stanford,
2016). Unlike :class:`aqp.strategies.hft.alphas.ImbalanceAlphaMM` which
*skews quotes around the mid* using imbalance, this strategy emits
asymmetric **directional** market orders when the multi-snapshot
imbalance pressure breaches a z-score threshold.

Math
====

For each event the strategy computes the canonical book imbalance

.. math::

    \\rho_t = \\frac{Q^{bid}_t - Q^{ask}_t}{Q^{bid}_t + Q^{ask}_t}.

A rolling window of ``window`` recent values yields the local mean
:math:`\\bar\\rho` and standard deviation :math:`\\sigma_\\rho`. The
strategy fires whenever

.. math::

    \\frac{\\rho_t - \\bar\\rho}{\\sigma_\\rho + \\epsilon}
    > \\tau_{\\text{enter}}

(long) or its negative (short), and exits when the z-score crosses
back through zero. Optional ``micropriceedge`` adds the microprice
deviation from mid as a confirmation filter so a single noisy
imbalance snapshot doesn't trigger.

Hard-rule compliance
====================

- ``@register("OBIDirectionalAlpha", source="research_report_2026")`` —
  AGENTS.md rule 8.
- Reuses :func:`aqp.data.microstructure.order_book_imbalance` and
  :func:`aqp.data.microstructure.microprice` (no duplicate math).
- No LLM / Iceberg / Postgres calls from the strategy body.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import logging

from aqp.core.registry import register
from aqp.data.microstructure import microprice, order_book_imbalance
from aqp.strategies.lob import LobState, LobStrategy, OrderIntent

logger = logging.getLogger(__name__)


@dataclass
class _ImbalanceState:
    window: deque[float] = field(default_factory=lambda: deque(maxlen=256))

    def push(self, value: float) -> None:
        self.window.append(value)

    def zscore(self, value: float) -> float:
        if len(self.window) < 4:
            return 0.0
        # Vectorised compute via Python — window <= 256 so this is fast
        # and stays import-cheap (no numpy import on hot path required).
        mu = sum(self.window) / len(self.window)
        var = sum((v - mu) ** 2 for v in self.window) / max(1, (len(self.window) - 1))
        sigma = var**0.5
        if sigma < 1e-9:
            return 0.0
        return (value - mu) / sigma


@register("OBIDirectionalAlpha", source="research_report_2026", category="microstructure")
class OBIDirectionalAlpha(LobStrategy):
    """Directional OBI alpha.

    Parameters
    ----------
    window
        Number of recent imbalance snapshots in the rolling baseline.
    enter_z
        Z-score threshold to enter (positive: long, negative: short).
    exit_z
        Z-score magnitude at which to flatten back to zero. Should be
        smaller than ``enter_z`` so the strategy doesn't whipsaw.
    order_size
        Quantity per directional order.
    max_position
        Hard inventory cap.
    microprice_edge_bps
        Optional microprice-vs-midprice confirmation in basis points.
        ``0`` disables; positive values require the microprice to lean
        in the signal direction by at least this many bps.
    """

    strategy_id = "obi_directional"

    def __init__(
        self,
        window: int = 64,
        enter_z: float = 2.0,
        exit_z: float = 0.3,
        order_size: float = 1.0,
        max_position: float = 10.0,
        microprice_edge_bps: float = 0.0,
    ) -> None:
        self.window = int(window)
        self.enter_z = float(enter_z)
        self.exit_z = float(exit_z)
        self.order_size = float(order_size)
        self.max_position = float(max_position)
        self.microprice_edge_bps = float(microprice_edge_bps)
        self._state = _ImbalanceState(window=deque(maxlen=self.window))

    def on_event(self, state: LobState) -> list[OrderIntent]:
        rho = float(order_book_imbalance(state.bid_qty, state.ask_qty))
        self._state.push(rho)
        z = self._state.zscore(rho)
        mid = state.mid_price
        intents: list[OrderIntent] = []

        if self.microprice_edge_bps > 0 and mid > 0:
            mp = float(
                microprice(state.best_bid, state.best_ask, state.bid_qty, state.ask_qty)
            )
            edge_bps = (mp - mid) / mid * 1e4
        else:
            edge_bps = 0.0

        # Exit logic: flatten when |z| collapses.
        if abs(z) < self.exit_z and abs(state.position) > 1e-9:
            side = "sell" if state.position > 0 else "buy"
            intents.append(
                OrderIntent(
                    side=side,
                    price=state.best_ask if side == "buy" else state.best_bid,
                    quantity=min(self.order_size, abs(state.position)),
                    order_type="market",
                    time_in_force="ioc",
                    post_only=False,
                    tag="obi_exit",
                )
            )
            return intents

        # Entry logic — directional market orders.
        if z > self.enter_z and state.position < self.max_position:
            if self.microprice_edge_bps == 0 or edge_bps >= self.microprice_edge_bps:
                intents.append(
                    OrderIntent(
                        side="buy",
                        price=state.best_ask,
                        quantity=self.order_size,
                        order_type="market",
                        time_in_force="ioc",
                        post_only=False,
                        tag="obi_long",
                    )
                )
        elif z < -self.enter_z and state.position > -self.max_position:
            if self.microprice_edge_bps == 0 or edge_bps <= -self.microprice_edge_bps:
                intents.append(
                    OrderIntent(
                        side="sell",
                        price=state.best_bid,
                        quantity=self.order_size,
                        order_type="market",
                        time_in_force="ioc",
                        post_only=False,
                        tag="obi_short",
                    )
                )
        return intents
