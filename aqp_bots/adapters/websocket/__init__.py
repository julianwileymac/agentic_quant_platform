"""Generic WebSocket adapter framework.

Provides reconnect / exponential backoff / msgspec JSON decode plumbing
so venue-specific WS adapters only need to implement the message-shape
translation. Concrete venue adapters subclass
:class:`WebsocketMarketDataAdapter` and override
:meth:`decode_message` to map venue JSON onto AQP's
:class:`MarketEvent` schemas.
"""
from __future__ import annotations

from aqp_bots.adapters.websocket.base import (
    BackoffPolicy,
    WebsocketAdapterError,
    WebsocketMarketDataAdapter,
)

__all__ = [
    "BackoffPolicy",
    "WebsocketAdapterError",
    "WebsocketMarketDataAdapter",
]
