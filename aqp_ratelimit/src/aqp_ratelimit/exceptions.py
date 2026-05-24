"""Exception hierarchy for the rate-limit subsystem."""
from __future__ import annotations


class RateLimitError(Exception):
    """Base class for rate-limit failures."""


class RateLimitExceeded(RateLimitError):
    """Raised when a bucket cannot satisfy the requested token count.

    Attributes
    ----------
    service:
        Logical service descriptor (``polygon.aggregates``).
    key_id:
        Per-user key identifier (UUID string or label).
    remaining:
        Tokens currently in the bucket after refill.
    requested:
        Tokens the caller asked for.
    retry_after_ms:
        Estimated milliseconds until the bucket refills enough to
        satisfy the request. Honoured by the Airbyte CDK
        ``RateLimitedHttpStream`` backoff and the Envoy 429 response.
    """

    def __init__(
        self,
        *,
        service: str,
        key_id: str,
        remaining: float,
        requested: int,
        retry_after_ms: int,
    ) -> None:
        self.service = service
        self.key_id = key_id
        self.remaining = remaining
        self.requested = requested
        self.retry_after_ms = retry_after_ms
        super().__init__(
            f"{service} budget exhausted for key {key_id}: "
            f"needed {requested}, had {remaining:.2f}; retry in {retry_after_ms}ms"
        )


class PolicyNotFoundError(RateLimitError):
    """Raised when a policy lookup for a given ``service`` finds nothing."""


class KeyRevokedError(RateLimitError):
    """Raised when the caller's :class:`RateLimitKey` row is revoked or expired."""


__all__ = [
    "KeyRevokedError",
    "PolicyNotFoundError",
    "RateLimitError",
    "RateLimitExceeded",
]
