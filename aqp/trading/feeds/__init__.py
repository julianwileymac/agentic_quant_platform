"""Async market data feeds.

The abstract contract lives in :mod:`aqp.core.interfaces` (``IMarketDataFeed``);
concrete venue-specific implementations live alongside this module. Venue
feeds are imported opportunistically so missing extras don't break the
package (mirrors the pattern used by :mod:`aqp.trading.brokerages`).
"""
from __future__ import annotations

import logging

from aqp.trading.feeds.base import BaseFeed, DeterministicReplayFeed
from aqp.trading.feeds.rest_poll import RestPollingFeed

logger = logging.getLogger(__name__)

__all__ = ["BaseFeed", "DeterministicReplayFeed", "RestPollingFeed"]

try:
    from aqp.trading.feeds.alpaca_feed import AlpacaDataFeed  # noqa: F401

    __all__.append("AlpacaDataFeed")
except ImportError as exc:  # pragma: no cover — optional extra
    logger.debug("AlpacaDataFeed unavailable: %s", exc)

try:
    from aqp.trading.feeds.ibkr_feed import IBKRDataFeed  # noqa: F401

    __all__.append("IBKRDataFeed")
except ImportError as exc:  # pragma: no cover
    logger.debug("IBKRDataFeed unavailable: %s", exc)

try:
    from aqp.trading.feeds.kafka_feed import KafkaDataFeed  # noqa: F401

    __all__.append("KafkaDataFeed")
except ImportError as exc:  # pragma: no cover
    logger.debug("KafkaDataFeed unavailable: %s", exc)
