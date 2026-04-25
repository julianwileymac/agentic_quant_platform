"""Typed Alpha Vantage errors and payload classification."""
from __future__ import annotations

from enum import StrEnum
from typing import Any


class RateLimitKind(StrEnum):
    RPM = "rpm"
    DAILY = "daily"


class AlphaVantageError(RuntimeError):
    """Base class for Alpha Vantage client failures."""


class AlphaVantageClientError(AlphaVantageError):
    """Back-compatible AQP error name used by existing call sites."""


class AlphaVantagePayloadError(AlphaVantageClientError):
    """Raised when Alpha Vantage returns an invalid or semantic error payload."""


class InvalidApiKeyError(AlphaVantageClientError):
    """Raised when no API key can be resolved."""


class InvalidSymbolError(AlphaVantagePayloadError):
    """Raised when Alpha Vantage reports an invalid symbol."""


class PremiumEndpointError(AlphaVantagePayloadError):
    """Raised when a premium-only endpoint is requested without entitlement."""


class TransientError(AlphaVantageClientError):
    """Raised for transient transport/server failures."""


class RateLimitError(AlphaVantageClientError):
    """Raised when a minute or daily rate limit is reached."""

    def __init__(
        self,
        message: str,
        *,
        kind: RateLimitKind = RateLimitKind.RPM,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retry_after_seconds = retry_after_seconds


def classify_payload(payload: Any) -> AlphaVantageClientError | None:
    """Return a typed error if an Alpha Vantage JSON payload carries one."""
    if not isinstance(payload, dict):
        return AlphaVantagePayloadError("Alpha Vantage returned a non-object JSON payload")

    message = ""
    for key in ("Error Message", "Information", "Note"):
        raw = str(payload.get(key) or "").strip()
        if raw:
            message = raw
            break
    if not message:
        return None

    lower = message.lower()
    if "invalid api call" in lower or "invalid api key" in lower:
        return InvalidApiKeyError(message)
    if "premium" in lower or "entitlement" in lower:
        return PremiumEndpointError(message)
    if "call frequency" in lower or "rate limit" in lower or "standard api rate limit" in lower:
        return RateLimitError(message, kind=RateLimitKind.RPM)
    if "symbol" in lower and ("invalid" in lower or "not found" in lower):
        return InvalidSymbolError(message)
    return AlphaVantagePayloadError(message)


__all__ = [
    "AlphaVantageClientError",
    "AlphaVantageError",
    "AlphaVantagePayloadError",
    "InvalidApiKeyError",
    "InvalidSymbolError",
    "PremiumEndpointError",
    "RateLimitError",
    "RateLimitKind",
    "TransientError",
    "classify_payload",
]
