"""Process-wide :class:`IngestionRateLimitFactory`.

Mirrors :class:`aqp.tenancy.factory.TenancyStrategyFactory`. The
factory picks the right :class:`IngestionRateLimitStrategy` instance
based on ``settings.ratelimit_default_strategy``. Singleton so the
underlying Redis / Lua script handles are shared process-wide.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from aqp_ratelimit.strategies.base import (
    INGESTION_RATELIMIT_STRATEGY_KIND,
    IngestionRateLimitStrategy,
    list_ratelimit_strategy_classes,
)

logger = logging.getLogger(__name__)


_FACTORY: IngestionRateLimitFactory | None = None
_FACTORY_LOCK = threading.RLock()


def _settings_default_strategy() -> str:
    try:
        from aqp.config import settings

        raw = str(
            getattr(settings, "ratelimit_default_strategy", "redis_token_bucket")
            or "redis_token_bucket"
        )
        return raw.lower()
    except Exception:  # noqa: BLE001
        return "redis_token_bucket"


def _find_strategy_class_by_kind(kind: str) -> type[IngestionRateLimitStrategy]:
    classes = list_ratelimit_strategy_classes()
    for cls in classes.values():
        if str(getattr(cls, "strategy_kind", "")).lower() == kind.lower():
            return cls
    # Fallback: in-memory always available.
    from aqp_ratelimit.strategies.in_memory import InMemoryStrategy

    return InMemoryStrategy


class IngestionRateLimitFactory:
    """Per-process resolver for :class:`IngestionRateLimitStrategy`."""

    def __init__(self) -> None:
        self._cache: dict[str, IngestionRateLimitStrategy] = {}

    def default(self) -> IngestionRateLimitStrategy:
        kind = _settings_default_strategy()
        return self._strategy_for(kind)

    def for_tenant(self, org_id: str | None) -> IngestionRateLimitStrategy:
        # Tenancy-aware routing reserved for future per-org strategy
        # overrides (e.g., a paying enterprise customer might get an
        # exclusive Redis db while default tenants share). For now
        # one default per process.
        return self.default()

    def for_kind(self, kind: str) -> IngestionRateLimitStrategy:
        return self._strategy_for(kind)

    def _strategy_for(self, kind: str) -> IngestionRateLimitStrategy:
        existing = self._cache.get(kind)
        if existing is not None:
            return existing
        cls = _find_strategy_class_by_kind(kind)
        try:
            instance = cls()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ratelimit factory: could not init %s (%s); falling back to in-memory",
                cls.__name__,
                exc,
            )
            from aqp_ratelimit.strategies.in_memory import InMemoryStrategy

            instance = InMemoryStrategy()
        self._cache[kind] = instance
        return instance


def get_ratelimit_factory() -> IngestionRateLimitFactory:
    """Return the process-wide :class:`IngestionRateLimitFactory`."""
    global _FACTORY
    if _FACTORY is None:
        with _FACTORY_LOCK:
            if _FACTORY is None:
                # Force-import the strategies module so the metaclass
                # has registered every concrete subclass before we
                # go looking for them.
                from aqp_ratelimit import strategies as _strategies  # noqa: F401

                _FACTORY = IngestionRateLimitFactory()
    return _FACTORY


def reset_ratelimit_factory() -> None:
    """Drop the singleton (tests + admin runbooks after policy rotation)."""
    global _FACTORY
    with _FACTORY_LOCK:
        _FACTORY = None


__all__ = [
    "IngestionRateLimitFactory",
    "get_ratelimit_factory",
    "reset_ratelimit_factory",
]
