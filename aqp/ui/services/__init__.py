"""Typed client-side wrappers around our FastAPI endpoints.

Pages should prefer these helpers over ``api_client.get/post`` directly
so response shapes stay consistent and error translation happens in a
single place.
"""
from aqp.ui.services.security import (
    IBKRAvailability,
    SecurityError,
    get_calendar,
    get_corporate,
    get_fundamentals,
    get_historical_bars,
    get_ibkr_availability,
    get_news,
    get_quote,
)

__all__ = [
    "IBKRAvailability",
    "SecurityError",
    "get_calendar",
    "get_corporate",
    "get_fundamentals",
    "get_historical_bars",
    "get_ibkr_availability",
    "get_news",
    "get_quote",
]
