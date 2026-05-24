"""Sync + async clients used by Fetchers, Dagster sensors, the CLI, and notebook kernels.

Every outbound vendor API call across the AQP stack threads through
one of these clients so the (user_id, service, key_id) accounting
stays consistent.

Public API:

    from aqp_ratelimit import get_ratelimit_client

    client = get_ratelimit_client()
    decision = client.check(
        user_id="user_abc",
        service="polygon.aggregates",
        key_id="key_primary",
    )
    if not decision.allow:
        raise RuntimeError(f"retry in {decision.retry_after_ms}ms")
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from aqp_ratelimit.factory import get_ratelimit_factory
from aqp_ratelimit.models import Decision, ReserveOutcome

logger = logging.getLogger(__name__)


class RateLimitClient:
    """Synchronous client wrapping the active strategy."""

    def __init__(self) -> None:
        self._factory = get_ratelimit_factory()

    def check(
        self,
        *,
        user_id: str,
        service: str,
        key_id: str,
        n_tokens: int = 1,
        ctx: dict[str, Any] | None = None,
        org_id: str | None = None,
    ) -> Decision:
        strategy = self._factory.for_tenant(org_id)
        return strategy.check(
            user_id=user_id,
            service=service,
            key_id=key_id,
            n_tokens=n_tokens,
            ctx=ctx,
        )

    def reserve(
        self,
        *,
        user_id: str,
        service: str,
        key_id: str,
        n_tokens: int,
        ttl_s: int = 3600,
        ctx: dict[str, Any] | None = None,
        org_id: str | None = None,
    ) -> ReserveOutcome:
        strategy = self._factory.for_tenant(org_id)
        return strategy.reserve(
            user_id=user_id,
            service=service,
            key_id=key_id,
            n_tokens=n_tokens,
            ttl_s=ttl_s,
            ctx=ctx,
        )

    def release(self, *, reservation_id: str, org_id: str | None = None) -> None:
        strategy = self._factory.for_tenant(org_id)
        strategy.release(reservation_id=reservation_id)

    def status(
        self,
        *,
        user_id: str,
        service: str,
        key_id: str,
        org_id: str | None = None,
    ) -> Decision:
        strategy = self._factory.for_tenant(org_id)
        return strategy.status(user_id=user_id, service=service, key_id=key_id)


class AsyncRateLimitClient:
    """Asyncio-friendly wrapper around :class:`RateLimitClient`.

    The current strategies are synchronous (Redis blocking calls are
    sub-millisecond). For now we run them in the default executor so
    the async surface stays uniform; future async-native strategies
    can override.
    """

    def __init__(self) -> None:
        self._sync = RateLimitClient()

    async def check(self, **kwargs: Any) -> Decision:
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._sync.check(**kwargs)
        )

    async def reserve(self, **kwargs: Any) -> ReserveOutcome:
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._sync.reserve(**kwargs)
        )

    async def release(self, *, reservation_id: str, org_id: str | None = None) -> None:
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._sync.release(reservation_id=reservation_id, org_id=org_id),
        )

    async def status(self, **kwargs: Any) -> Decision:
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._sync.status(**kwargs)
        )


_CLIENT: RateLimitClient | None = None
_ASYNC_CLIENT: AsyncRateLimitClient | None = None
_CLIENT_LOCK = threading.RLock()


def get_ratelimit_client() -> RateLimitClient:
    """Return the process-wide synchronous client singleton."""
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                _CLIENT = RateLimitClient()
    return _CLIENT


def get_async_ratelimit_client() -> AsyncRateLimitClient:
    """Return the process-wide async client singleton."""
    global _ASYNC_CLIENT
    if _ASYNC_CLIENT is None:
        with _CLIENT_LOCK:
            if _ASYNC_CLIENT is None:
                _ASYNC_CLIENT = AsyncRateLimitClient()
    return _ASYNC_CLIENT


__all__ = [
    "AsyncRateLimitClient",
    "RateLimitClient",
    "get_async_ratelimit_client",
    "get_ratelimit_client",
]
