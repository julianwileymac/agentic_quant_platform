"""Limit-order-book strategy ABC (stub).

Engine integration is deferred — see
``extractions/_FUTURE_PROMPTS/lob_adapter_prompt.md`` for the full prompt
that drives the future hftbacktest LOB adapter implementation.

Today this file provides:
- ``OrderIntent`` dataclass — the minimal order schema strategies emit.
- ``LobStrategy`` ABC — every HFT strategy under ``aqp/strategies/hft/``
  subclasses this.
- ``LobState`` dataclass — what the engine passes into ``on_event``.

Strategies authored against this contract are wired through the future
``aqp/backtest/hft.py::LobBacktestEngine``. Until then they list under
``/data/microstructure`` in the UI as "Engine pending".
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
    primitives (`hbt.submit_buy_order`, `hbt.submit_sell_order`).
    """

    side: Literal["buy", "sell"]
    price: float
    quantity: float
    order_type: Literal["limit", "market"] = "limit"
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
    update. The future LOB engine drives this loop; until the engine
    ships, strategies that try to run will raise ``NotImplementedError``
    via :meth:`run`.
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

    def run(self, *args, **kwargs):
        """Stub entry point — engine integration is deferred.

        See ``extractions/_FUTURE_PROMPTS/lob_adapter_prompt.md`` for the
        future-work spec; the ``LobBacktestEngine`` will replace this
        method with a real driver loop.
        """
        raise NotImplementedError(
            "LOB engine integration is deferred. See "
            "extractions/_FUTURE_PROMPTS/lob_adapter_prompt.md for the next step."
        )


__all__ = ["LobState", "LobStrategy", "OrderIntent"]
