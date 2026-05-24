"""Composite tenancy strategy: route per-organization (Workstream F).

The hybrid strategy is the production default. It looks up
``Organization.tenancy_strategy`` and dispatches to the matching
concrete strategy. Operators flip the org-level column to migrate a
single tenant between models — e.g. a mid-tier customer ascending to
enterprise gets ``database_per_enterprise`` set on their org row, and
the next session lands on a dedicated cluster.

Lookups go through a tiny in-process cache so we don't issue a
``SELECT tenancy_strategy FROM organizations`` on every session
checkout; the cache TTL is short (30 s) so operators see the new
strategy within one TTL after they flip the column.

Phase 7 of the Auth0 Refactor adds Redis pub/sub-based cross-worker
cache invalidation: when an admin flips an org's strategy via the
:func:`/tenancy/orgs/{org_id}/migrate-strategy` endpoint, the
backend publishes a ``{org_id}`` payload to
``aqp:tenancy:strategy_changed``. Every worker subscribes on boot
and drops the matching cache entry on receipt, so the flip
propagates within one Redis round trip instead of waiting out the
30s TTL. The pub/sub subscriber is best-effort; the TTL remains
the authoritative cap so a network blip can't permanently strand
a stale entry.
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncContextManager

from aqp.tenancy.protocol import TenancyStrategy, TenancyStrategyError
from aqp.tenancy.strategies.database_per_enterprise import DatabasePerEnterpriseStrategy
from aqp.tenancy.strategies.schema_per_tenant import SchemaPerTenantStrategy
from aqp.tenancy.strategies.shared_schema_rls import SharedSchemaRLSStrategy

# Pub/sub channel for cross-worker invalidation. The publisher
# writes the bare ``org_id`` as the payload; the subscriber drops
# the matching cache entry. Reserved channel name (only the
# tenancy strategy uses it).
STRATEGY_CHANGED_CHANNEL: str = "aqp:tenancy:strategy_changed"

logger = logging.getLogger(__name__)


_STRATEGY_CACHE: dict[str, tuple[float, str]] = {}
_STRATEGY_LOCK = threading.RLock()
_STRATEGY_TTL_SECONDS = 30.0


def _settings_default() -> str:
    try:
        from aqp.config import settings

        raw = str(
            getattr(settings, "tenancy_default_strategy", "shared_schema_rls") or "shared_schema_rls"
        )
        return raw.lower()
    except Exception:  # noqa: BLE001
        return "shared_schema_rls"


class HybridStrategy(TenancyStrategy):
    """Composite strategy that routes per-organization."""

    strategy_kind = "hybrid"
    strategy_alias = "HybridStrategy"

    def __init__(self) -> None:
        self._rls = SharedSchemaRLSStrategy()
        self._schema = SchemaPerTenantStrategy()
        self._db = DatabasePerEnterpriseStrategy()

    def session(self, org_id: str | None) -> AsyncContextManager[Any]:
        return _hybrid_session_cm(self, org_id)

    async def onboard(self, org_id: str, profile: dict[str, Any]) -> None:
        strategy = self._resolve_strategy_class(org_id)
        await strategy.onboard(org_id, profile)

    async def offboard(self, org_id: str) -> None:
        strategy = self._resolve_strategy_class(org_id)
        await strategy.offboard(org_id)

    # ------------------------------------------------------------------
    # Internal: resolve org -> concrete strategy
    # ------------------------------------------------------------------

    def _resolve_strategy_class(self, org_id: str | None) -> TenancyStrategy:
        kind = _lookup_org_strategy(org_id) if org_id else _settings_default()
        if kind == "database_per_enterprise":
            return self._db
        if kind == "schema_per_tenant":
            return self._schema
        return self._rls


def _lookup_org_strategy(org_id: str | None) -> str:
    """Return the configured strategy kind for ``org_id``, cached."""
    if not org_id:
        return _settings_default()
    key = str(org_id)
    now = time.monotonic()
    with _STRATEGY_LOCK:
        cached = _STRATEGY_CACHE.get(key)
        if cached is not None:
            expires_at, value = cached
            if now < expires_at:
                return value

    value = _settings_default()
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import Organization

        with get_session() as session:
            org = (
                session.query(Organization)
                .filter(Organization.id == key)
                .one_or_none()
            )
            if org is not None:
                strat = getattr(org, "tenancy_strategy", None)
                if strat:
                    value = str(strat).lower()
    except Exception:  # noqa: BLE001
        # Fall back to the default when the table doesn't yet have the
        # column (migration 0063 hasn't been applied) or any other
        # transient error.
        logger.debug("strategy lookup fallback for org_id=%s", org_id, exc_info=True)

    with _STRATEGY_LOCK:
        _STRATEGY_CACHE[key] = (now + _STRATEGY_TTL_SECONDS, value)
    return value


@asynccontextmanager
async def _hybrid_session_cm(strategy: HybridStrategy, org_id: str | None) -> Any:
    concrete = strategy._resolve_strategy_class(org_id)
    async with concrete.session(org_id) as session:
        yield session


def reset_strategy_cache() -> None:
    """Drop the org->strategy cache (used by tests + after admin flips)."""
    with _STRATEGY_LOCK:
        _STRATEGY_CACHE.clear()


def invalidate_org(org_id: str) -> None:
    """Drop a single org's cached strategy entry.

    Called by :func:`publish_strategy_changed` after the publisher
    has flipped the column, and by the local pub/sub subscriber on
    every received message so peers stay in sync.
    """
    if not org_id:
        return
    key = str(org_id)
    with _STRATEGY_LOCK:
        _STRATEGY_CACHE.pop(key, None)


def publish_strategy_changed(org_id: str) -> bool:
    """Announce a strategy change to every worker via Redis pub/sub.

    Drops the local cache entry IMMEDIATELY (so the publisher worker
    doesn't have to wait for its own pub/sub round trip) and then
    publishes the bare ``org_id`` on
    :data:`STRATEGY_CHANGED_CHANNEL`. Returns ``True`` when the
    publish succeeded; ``False`` (logged) when Redis is unreachable
    so the caller can decide whether to surface a warning to the
    operator. Workers without an active subscriber still pick up
    the change within the existing TTL.
    """
    invalidate_org(org_id)
    try:
        client = _redis_client()
        if client is None:
            return False
        client.publish(STRATEGY_CHANGED_CHANNEL, str(org_id))
        return True
    except Exception:  # noqa: BLE001
        logger.debug("strategy change publish failed", exc_info=True)
        return False


def _redis_client() -> Any:
    """Return a synchronous Redis client or ``None`` when unreachable.

    Mirrors :func:`aqp.ws.broker.publish` so the same Redis URL +
    decode_responses config are used. Catches every exception so
    a Redis outage never blocks the strategy lookup path.
    """
    try:
        import redis  # type: ignore[import-not-found]

        from aqp.config import settings

        return redis.Redis.from_url(settings.redis_pubsub_url, decode_responses=True)
    except Exception:  # noqa: BLE001
        return None


def start_strategy_invalidation_subscriber() -> threading.Thread | None:
    """Spawn a daemon thread that subscribes to strategy-change events.

    Idempotent — calling twice returns the existing thread. Best-
    effort; if Redis is unreachable at boot we silently no-op, the
    30s TTL keeps drift bounded.

    Call this once at backend boot (FastAPI lifespan) so every
    worker process picks up admin-driven strategy flips without
    waiting for their cache TTL to expire.
    """
    global _SUBSCRIBER_THREAD
    if _SUBSCRIBER_THREAD is not None and _SUBSCRIBER_THREAD.is_alive():
        return _SUBSCRIBER_THREAD
    client = _redis_client()
    if client is None:
        return None

    def _loop() -> None:
        try:
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(STRATEGY_CHANGED_CHANNEL)
            for message in pubsub.listen():
                if message is None:
                    continue
                if message.get("type") != "message":
                    continue
                raw = message.get("data")
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                if isinstance(raw, str) and raw:
                    invalidate_org(raw)
        except Exception:  # noqa: BLE001
            logger.warning("strategy invalidation subscriber crashed", exc_info=True)

    thread = threading.Thread(
        target=_loop,
        name="aqp-tenancy-strategy-invalidator",
        daemon=True,
    )
    thread.start()
    _SUBSCRIBER_THREAD = thread
    return thread


_SUBSCRIBER_THREAD: threading.Thread | None = None


__all__ = [
    "HybridStrategy",
    "STRATEGY_CHANGED_CHANNEL",
    "invalidate_org",
    "publish_strategy_changed",
    "reset_strategy_cache",
    "start_strategy_invalidation_subscriber",
]
