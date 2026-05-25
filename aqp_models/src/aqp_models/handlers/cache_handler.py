"""CacheHandler — process-local LRU cache of loaded model artifacts.

The cache sits in front of :class:`LoadHandler` so repeated agent
inference calls do not re-pull and re-deserialise multi-gigabyte
foundation models from the object store. Eviction is LRU by default
and respects two budgets:

- ``max_entries`` from ``settings.ml_cache_max_entries`` (default 16).
- ``max_vram_bytes`` from ``settings.ml_cache_max_vram_bytes`` (best-
  effort, measured by ``estimate_size`` callbacks; defaults to 32 GB).

Optionally synchronises with the platform's ``ml_cache_entries``
Postgres table so the operator UI can render the current cache state
across workers. The Postgres sync is best-effort — when the table /
session is unavailable the cache still works in-process.
"""
from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from aqp_models.handlers.base import (
    HandlerContext,
    HandlerResult,
    MLOpsHandler,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CachedModel:
    """One in-memory cache entry."""

    key: str
    model: Any
    size_bytes: int = 0
    last_access: datetime = field(default_factory=datetime.utcnow)
    hits: int = 0
    extras: dict[str, Any] = field(default_factory=dict)

    def to_descriptor(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "model_class": self.model.__class__.__name__,
            "size_bytes": int(self.size_bytes),
            "last_access": self.last_access.isoformat(),
            "hits": int(self.hits),
            "extras": dict(self.extras),
        }


class CacheHandler(MLOpsHandler):
    """Process-local LRU cache + best-effort Postgres mirror.

    Supports four operations through :meth:`run` (dispatched by the
    ``op`` kwarg the route / MCP tool sends):

    - ``warm`` — call the loader and seed the cache.
    - ``get`` — return the cached entry (no-op when missing).
    - ``evict`` — drop a specific key.
    - ``stats`` — list every entry currently in the cache.
    """

    handler_name = "ml.cache"
    required_scopes = ("data:read",)
    mutates = True  # warm / evict mutate process state

    def __init__(
        self,
        *,
        max_entries: int | None = None,
        max_vram_bytes: int | None = None,
        size_estimator: Callable[[Any], int] | None = None,
    ) -> None:
        super().__init__()
        self._lock = threading.RLock()
        self._cache: OrderedDict[str, CachedModel] = OrderedDict()
        self._max_entries = int(max_entries) if max_entries is not None else _settings_int(
            "ml_cache_max_entries", 16
        )
        self._max_vram_bytes = (
            int(max_vram_bytes) if max_vram_bytes is not None else _settings_int(
                "ml_cache_max_vram_bytes", 32 * 1024**3
            )
        )
        self._size_estimator = size_estimator or _default_size_estimator

    # ------------------------------------------------------------------
    # MLOpsHandler entry point
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        ctx: HandlerContext,
        op: str = "stats",
        key: str | None = None,
        loader: Callable[[], Any] | None = None,
        extras: dict[str, Any] | None = None,
        **_: Any,
    ) -> HandlerResult:
        op = (op or "stats").lower()
        if op == "warm":
            if not key:
                return HandlerResult(ok=False, error="cache warm requires ``key``")
            if loader is None:
                return HandlerResult(
                    ok=False, error="cache warm requires a ``loader`` callable"
                )
            entry = self._warm(key=key, loader=loader, extras=extras)
            self._mirror_to_postgres(entry, op="warm", ctx=ctx)
            return HandlerResult(
                ok=True,
                data=entry.to_descriptor(),
                summary=f"warmed {key}",
                metadata={"op": "warm"},
            )

        if op == "get":
            if not key:
                return HandlerResult(ok=False, error="cache get requires ``key``")
            entry = self._touch(key)
            if entry is None:
                return HandlerResult(
                    ok=False,
                    error=f"key {key!r} not in cache",
                    metadata={"op": "get"},
                )
            return HandlerResult(
                ok=True,
                data=entry.to_descriptor(),
                summary=f"hit {key}",
                metadata={"op": "get"},
            )

        if op == "evict":
            if not key:
                return HandlerResult(ok=False, error="cache evict requires ``key``")
            with self._lock:
                removed = self._cache.pop(key, None)
            self._mirror_to_postgres(removed, op="evict", ctx=ctx) if removed else None
            return HandlerResult(
                ok=True,
                data={"evicted": removed.to_descriptor() if removed else None},
                summary=f"evicted {key}" if removed else f"not cached: {key}",
                metadata={"op": "evict"},
            )

        if op == "stats":
            with self._lock:
                entries = [e.to_descriptor() for e in self._cache.values()]
                total_bytes = sum(e.size_bytes for e in self._cache.values())
            return HandlerResult(
                ok=True,
                data={
                    "entries": entries,
                    "total_bytes": int(total_bytes),
                    "max_entries": self._max_entries,
                    "max_vram_bytes": self._max_vram_bytes,
                },
                summary=f"{len(entries)} entries",
                metadata={"op": "stats"},
            )

        return HandlerResult(
            ok=False, error=f"unknown cache op {op!r}", metadata={"op": op}
        )

    # ------------------------------------------------------------------
    # Public (callable from Python without going through ``invoke``)
    # ------------------------------------------------------------------

    def lookup(self, key: str) -> CachedModel | None:
        return self._touch(key)

    def warm(
        self,
        *,
        key: str,
        loader: Callable[[], Any],
        extras: dict[str, Any] | None = None,
    ) -> CachedModel:
        return self._warm(key=key, loader=loader, extras=extras)

    def evict(self, key: str) -> CachedModel | None:
        with self._lock:
            return self._cache.pop(key, None)

    def clear(self) -> int:
        with self._lock:
            n = len(self._cache)
            self._cache.clear()
            return n

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "n_entries": len(self._cache),
                "max_entries": self._max_entries,
                "max_vram_bytes": self._max_vram_bytes,
                "total_bytes": sum(e.size_bytes for e in self._cache.values()),
                "entries": [e.to_descriptor() for e in self._cache.values()],
            }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _touch(self, key: str) -> CachedModel | None:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            entry.last_access = datetime.utcnow()
            entry.hits += 1
            self._cache.move_to_end(key)
            return entry

    def _warm(
        self,
        *,
        key: str,
        loader: Callable[[], Any],
        extras: dict[str, Any] | None,
    ) -> CachedModel:
        with self._lock:
            existing = self._cache.get(key)
            if existing is not None:
                existing.last_access = datetime.utcnow()
                existing.hits += 1
                self._cache.move_to_end(key)
                return existing

        # Load outside the lock so a slow loader does not block other
        # cache operations.
        model = loader()
        size = max(int(self._size_estimator(model)), 0)
        entry = CachedModel(
            key=key,
            model=model,
            size_bytes=size,
            last_access=datetime.utcnow(),
            extras=dict(extras or {}),
        )

        with self._lock:
            self._cache[key] = entry
            self._cache.move_to_end(key)
            self._enforce_budgets_locked()
        return entry

    def _enforce_budgets_locked(self) -> None:
        # Evict by LRU until both budgets are respected.
        while len(self._cache) > self._max_entries:
            evicted_key, _ = self._cache.popitem(last=False)
            logger.info("cache eviction (max_entries) %s", evicted_key)

        total = sum(e.size_bytes for e in self._cache.values())
        while total > self._max_vram_bytes and self._cache:
            evicted_key, evicted = self._cache.popitem(last=False)
            total -= evicted.size_bytes
            logger.info("cache eviction (max_vram_bytes) %s", evicted_key)

    def _mirror_to_postgres(
        self,
        entry: CachedModel | None,
        *,
        op: str,
        ctx: HandlerContext,
    ) -> None:
        """Best-effort row write into ``ml_cache_entries``.

        Wrapped in a broad ``except`` because process-local cache state
        must keep working even when the migration has not been applied
        yet or Postgres is unreachable.
        """
        if entry is None:
            return
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models_mlops import MlCacheEntry

            with get_session() as session:
                row = (
                    session.query(MlCacheEntry)
                    .filter(MlCacheEntry.key == entry.key)
                    .one_or_none()
                )
                if op == "evict":
                    if row is not None:
                        row.evicted_at = datetime.utcnow()
                    return
                if row is None:
                    row = MlCacheEntry(
                        key=entry.key,
                        model_class=entry.model.__class__.__name__,
                        size_bytes=entry.size_bytes,
                        hits=entry.hits,
                        last_access=entry.last_access,
                        workspace_id=ctx.workspace_id,
                        project_id=ctx.project_id,
                        owner_user_id=ctx.actor if ctx.actor_kind == "user" else None,
                    )
                    session.add(row)
                else:
                    row.size_bytes = entry.size_bytes
                    row.hits = entry.hits
                    row.last_access = entry.last_access
                    row.evicted_at = None
        except Exception:  # noqa: BLE001
            logger.debug("cache postgres mirror failed", exc_info=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings_int(name: str, default: int) -> int:
    try:
        from aqp.config import settings  # type: ignore[import-not-found]

        return int(getattr(settings, name, default))
    except Exception:  # noqa: BLE001
        return int(default)


def _default_size_estimator(model: Any) -> int:
    """Best-effort byte-count for a loaded model.

    Handles torch ``nn.Module``, qlib-style ``BaseModel`` wrappers that
    keep an ``.model`` torch attribute, sklearn estimators (via
    ``pickle.dumps`` byte length as a proxy), and ``transformers``
    pipelines (sum of parameter byte sizes when possible). Falls back
    to 0 for anything we can't measure cheaply.
    """
    try:
        import torch

        # Direct torch module
        if isinstance(model, torch.nn.Module):
            return _torch_module_bytes(model)
        # Wrappers keep a ``.model`` attr (qlib pattern)
        inner = getattr(model, "model", None)
        if isinstance(inner, torch.nn.Module):
            return _torch_module_bytes(inner)
        # transformers pipeline
        inner_pipeline = getattr(model, "pipeline_", None)
        if inner_pipeline is not None:
            pipe_model = getattr(inner_pipeline, "model", None)
            if isinstance(pipe_model, torch.nn.Module):
                return _torch_module_bytes(pipe_model)
    except Exception:  # noqa: BLE001
        pass

    try:
        import pickle

        return len(pickle.dumps(model))
    except Exception:  # noqa: BLE001
        return 0


def _torch_module_bytes(mod: Any) -> int:
    """Sum parameter byte-sizes for a ``torch.nn.Module``."""
    try:
        return int(
            sum(p.numel() * p.element_size() for p in mod.parameters())
        )
    except Exception:  # noqa: BLE001
        return 0


__all__ = ["CachedModel", "CacheHandler"]
