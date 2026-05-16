"""Limit-order-book strategy contract.

Three primitives:

- :class:`OrderIntent` — the minimal order schema a ``LobStrategy``
  emits, designed to map 1:1 onto ``hftbacktest`` order primitives
  (``hbt.submit_buy_order`` / ``hbt.submit_sell_order`` /
  ``hbt.cancel`` / ``hbt.elapse``).
- :class:`LobState` — the per-event snapshot the engine passes into
  ``on_event``.
- :class:`LobStrategy` — the ABC every HFT strategy under
  :mod:`aqp.strategies.hft` subclasses.

The driver is :class:`aqp.backtest.hft.LobBacktestEngine`. When the
``[hft]`` extra is not installed, calling :meth:`LobStrategy.run`
raises an :class:`ImportError` with install instructions instead of
``NotImplementedError``.

Helper methods on :class:`LobStrategy`
======================================

The ABC ships three helper methods that strategy bodies use to build
``OrderIntent`` records without re-implementing the same boilerplate:

- :meth:`buy` — emit a buy intent.
- :meth:`sell` — emit a sell intent.
- :meth:`cancel_all` — emit a synthetic ``OrderIntent(order_type="cancel")``
  the engine translates into ``hbt.cancel(order_id)`` for every live order.

Subclasses still override :meth:`on_event` to express the actual signal
math; the helpers just keep the bodies pure-Python and import-cheap.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrderIntent:
    """Minimal LOB-aware order intent.

    Fields chosen to map cleanly onto ``hftbacktest`` order submission
    primitives (``hbt.submit_buy_order``, ``hbt.submit_sell_order``,
    ``hbt.cancel``).

    A ``cancel`` intent uses ``order_type="cancel"`` and carries the
    ``order_id`` to cancel via the ``tag`` field. The engine translates
    that into ``hbt.cancel(asset_no, order_id)`` directly.
    """

    side: Literal["buy", "sell"]
    price: float
    quantity: float
    order_type: Literal["limit", "market", "cancel"] = "limit"
    time_in_force: Literal["gtc", "ioc", "fok", "gtx"] = "gtc"
    post_only: bool = True
    tag: str | None = None


@dataclass
class LobState:
    """Snapshot of the LOB at one event tick."""

    timestamp: datetime
    asset_no: int
    best_bid: float
    best_ask: float
    bid_qty: float
    ask_qty: float
    position: float
    cash: float
    bid_prices: np.ndarray | None = None
    ask_prices: np.ndarray | None = None
    bid_qtys: np.ndarray | None = None
    ask_qtys: np.ndarray | None = None
    last_trade_price: float | None = None
    last_trade_qty: float | None = None
    extras: dict = field(default_factory=dict)

    @property
    def mid_price(self) -> float:
        return (self.best_bid + self.best_ask) / 2.0

    @property
    def spread(self) -> float:
        return self.best_ask - self.best_bid


class LobStrategy(ABC):
    """ABC for limit-order-book strategies.

    Subclasses implement :meth:`on_event` to react to each book/trade
    update. The driver is :class:`aqp.backtest.hft.LobBacktestEngine`.
    """

    strategy_id: str = "lob_strategy"

    @abstractmethod
    def on_event(self, state: LobState) -> list[OrderIntent]:
        """Produce zero or more order intents in response to a state update."""

    def on_book_update(self, state: LobState) -> list[OrderIntent]:
        """Optional override for depth-only updates. Defaults to ``on_event``."""
        return self.on_event(state)

    def on_trade(self, state: LobState) -> list[OrderIntent]:
        """Optional override for trade-tick updates. Defaults to ``on_event``."""
        return self.on_event(state)

    # ------------------------------------------------------------------
    # OrderIntent builder helpers (keep ``on_event`` bodies concise).
    # ------------------------------------------------------------------

    @staticmethod
    def buy(
        price: float,
        quantity: float,
        *,
        post_only: bool = True,
        time_in_force: Literal["gtc", "ioc", "fok", "gtx"] = "gtc",
        order_type: Literal["limit", "market"] = "limit",
        tag: str | None = None,
    ) -> OrderIntent:
        """Construct a buy :class:`OrderIntent`."""
        return OrderIntent(
            side="buy",
            price=float(price),
            quantity=float(quantity),
            post_only=post_only,
            time_in_force=time_in_force,
            order_type=order_type,
            tag=tag,
        )

    @staticmethod
    def sell(
        price: float,
        quantity: float,
        *,
        post_only: bool = True,
        time_in_force: Literal["gtc", "ioc", "fok", "gtx"] = "gtc",
        order_type: Literal["limit", "market"] = "limit",
        tag: str | None = None,
    ) -> OrderIntent:
        """Construct a sell :class:`OrderIntent`."""
        return OrderIntent(
            side="sell",
            price=float(price),
            quantity=float(quantity),
            post_only=post_only,
            time_in_force=time_in_force,
            order_type=order_type,
            tag=tag,
        )

    @staticmethod
    def cancel(order_id: str, *, side: Literal["buy", "sell"] = "buy") -> OrderIntent:
        """Construct a cancel intent. The engine maps ``tag`` to ``hbt.cancel``."""
        return OrderIntent(
            side=side,
            price=0.0,
            quantity=0.0,
            order_type="cancel",
            tag=order_id,
        )

    def run(self, *args, **kwargs):
        """Run this strategy through :class:`LobBacktestEngine`.

        Available only when the ``[hft]`` extra is installed (which
        provides ``hftbacktest>=2.0``). Without it, the import below
        raises :class:`ImportError` with install instructions.
        """
        from aqp.backtest.hft import LobBacktestEngine

        engine = LobBacktestEngine()
        return engine.run(self, *args, **kwargs)


__all__ = ["LobState", "LobStrategy", "OrderIntent"]
