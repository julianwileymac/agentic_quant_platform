"""Process-wide :class:`TenancyStrategyFactory` (Workstream F).

The factory picks the right :class:`TenancyStrategy` instance based on
``settings.tenancy_default_strategy`` (when there's no per-org
override) or :class:`HybridStrategy` (when the deployment routes per
organisation). Singleton so the engine caches inside individual
strategies are shared across the process.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, AsyncContextManager

from aqp.tenancy.protocol import (
    TENANCY_STRATEGY_KIND,
    TenancyStrategy,
    TenancyStrategyError,
    list_tenancy_strategy_classes,
)

logger = logging.getLogger(__name__)


_FACTORY: TenancyStrategyFactory | None = None
_FACTORY_LOCK = threading.RLock()


def _settings_default_strategy() -> str:
    try:
        from aqp.config import settings

        raw = str(
            getattr(settings, "tenancy_default_strategy", "shared_schema_rls")
            or "shared_schema_rls"
        )
        return raw.lower()
    except Exception:  # noqa: BLE001
        return "shared_schema_rls"


def _find_strategy_class_by_kind(kind: str) -> type[TenancyStrategy]:
    classes = list_tenancy_strategy_classes()
    for cls in classes.values():
        if str(getattr(cls, "strategy_kind", "")).lower() == kind.lower():
            return cls
    raise TenancyStrategyError(
        f"no TenancyStrategy registered for kind={kind!r}"
    )


class TenancyStrategyFactory:
    """Per-process tenancy strategy resolver.

    The factory holds one strategy instance per kind plus a top-level
    "default" instance built from
    ``settings.tenancy_default_strategy``. Callers ask for either:

    - the default strategy via :meth:`default()` — used by background
      tasks and admin endpoints that aren't request-bound;
    - the strategy for a specific organisation via
      :meth:`for_organization(org_id)` — usually a :class:`HybridStrategy`
      that dispatches per-org under the hood.
    """

    def __init__(self) -> None:
        self._cache: dict[str, TenancyStrategy] = {}

    def default(self) -> TenancyStrategy:
        kind = _settings_default_strategy()
        return self._strategy_for(kind)

    def for_organization(self, org_id: str | None) -> TenancyStrategy:
        kind = _settings_default_strategy()
        return self._strategy_for(kind)

    def for_kind(self, kind: str) -> TenancyStrategy:
        return self._strategy_for(kind)

    def session(self, org_id: str | None) -> AsyncContextManager[Any]:
        return self.for_organization(org_id).session(org_id)

    def _strategy_for(self, kind: str) -> TenancyStrategy:
        existing = self._cache.get(kind)
        if existing is not None:
            return existing
        cls = _find_strategy_class_by_kind(kind)
        instance = cls()
        self._cache[kind] = instance
        return instance


def get_tenancy_factory() -> TenancyStrategyFactory:
    """Return the process-wide :class:`TenancyStrategyFactory`."""
    global _FACTORY
    if _FACTORY is None:
        with _FACTORY_LOCK:
            if _FACTORY is None:
                # Force-import the strategies module so the metaclass
                # has had a chance to register every concrete subclass
                # before we go looking for them.
                from aqp.tenancy import strategies as _strategies  # noqa: F401

                _FACTORY = TenancyStrategyFactory()
    return _FACTORY


def reset_tenancy_factory() -> None:
    """Drop the singleton (tests + admin runbooks after rotation)."""
    global _FACTORY
    with _FACTORY_LOCK:
        _FACTORY = None


__all__ = [
    "TenancyStrategyFactory",
    "get_tenancy_factory",
    "reset_tenancy_factory",
]
