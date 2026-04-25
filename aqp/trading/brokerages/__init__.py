"""Concrete broker adapters — paper and live venues.

Each adapter lives in its own module and declares an optional dependency in
:mod:`pyproject.toml`::

    pip install -e ".[alpaca]"   # AlpacaBrokerage
    pip install -e ".[ibkr]"     # InteractiveBrokersBrokerage
    pip install -e ".[tradier]"  # TradierBrokerage

The class registrations happen at import time so every broker is reachable
via :func:`aqp.core.registry.build_from_config` with just its class name.
The imports are wrapped in ``try/except ImportError`` so missing extras
never break the package.
"""
from __future__ import annotations

import logging

from aqp.trading.brokerages.base import BaseAsyncBrokerage, RateLimiter, traced_broker_call

logger = logging.getLogger(__name__)

__all__ = ["BaseAsyncBrokerage", "RateLimiter", "traced_broker_call"]

try:
    from aqp.trading.brokerages.alpaca import AlpacaBrokerage  # noqa: F401

    __all__.append("AlpacaBrokerage")
except ImportError as exc:  # pragma: no cover — optional extra
    logger.debug("AlpacaBrokerage unavailable: %s", exc)

try:
    from aqp.trading.brokerages.ibkr import InteractiveBrokersBrokerage  # noqa: F401

    __all__.append("InteractiveBrokersBrokerage")
except ImportError as exc:  # pragma: no cover
    logger.debug("InteractiveBrokersBrokerage unavailable: %s", exc)

try:
    from aqp.trading.brokerages.tradier import TradierBrokerage  # noqa: F401

    __all__.append("TradierBrokerage")
except ImportError as exc:  # pragma: no cover
    logger.debug("TradierBrokerage unavailable: %s", exc)
