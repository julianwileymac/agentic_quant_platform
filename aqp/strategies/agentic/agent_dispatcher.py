"""Per-bar agent dispatcher for event-driven strategies.

The vbt-pro engine's per-bar callbacks are Numba-jit only and cannot host
LLM calls. Strategies that need to **consult an agent inside the bar loop**
must run on the event-driven engine, which is pure Python. This module
provides the canonical primitive for that path:

::

    # Inside an IStrategy.on_bar:
    decision = context["agents"].consult(
        spec_name="trader.signal_emitter",
        inputs={"vt_symbol": bar.symbol.vt_symbol, "as_of": bar.timestamp},
        ttl=timedelta(hours=1),
    )

The dispatcher batches and de-duplicates calls via a TTL-aware in-memory
LRU plus the persistent :class:`DecisionCache`, so a strategy is free to
issue ``consult`` on every bar without hammering the LLM.

For async contexts, use :meth:`AgentDispatcher.consult_async` which runs
the underlying :class:`AgentRuntime.run` on a worker thread.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Mapping

from aqp.core.registry import register

logger = logging.getLogger(__name__)


def _stable_hash(payload: Mapping[str, Any]) -> str:
    """Hash an inputs dict with a stable, recursive JSON encoding."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@register("AgentDispatcher")
class AgentDispatcher:
    """Cache-fronted agent caller for use inside per-bar strategy code.

    Parameters
    ----------
    ttl_seconds:
        Default TTL for cached agent results. ``None`` disables time-based
        eviction (entries live until the LRU evicts them).
    cache_size:
        Max entries in the in-memory LRU.
    decision_cache:
        Optional :class:`aqp.agents.trading.decision_cache.DecisionCache` for
        persistence across runs. When set, every successful consult is also
        upserted to the persistent store.
    use_runtime:
        When True (default), :meth:`consult` invokes
        :func:`aqp.agents.runtime.runtime_for(spec_name).run(inputs)`. When
        False, :meth:`consult` only reads from the persistent cache (useful
        for replays / deterministic tests).
    """

    def __init__(
        self,
        *,
        ttl_seconds: float | None = 3600.0,
        cache_size: int = 4096,
        decision_cache: Any | None = None,
        use_runtime: bool = True,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.cache_size = int(cache_size)
        self.decision_cache = decision_cache
        self.use_runtime = bool(use_runtime)
        self._lru: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.RLock()
        self.stats: dict[str, int] = {
            "consults": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "runtime_calls": 0,
            "errors": 0,
        }

    # ------------------------------------------------------------------
    # Sync API
    # ------------------------------------------------------------------

    def consult(
        self,
        spec_name: str,
        inputs: Mapping[str, Any] | None = None,
        *,
        ttl: timedelta | float | None = None,
    ) -> Any:
        """Look up or run an agent and return its :class:`AgentRunResult`.

        Returns ``None`` on cache miss when ``use_runtime`` is False.
        """
        self.stats["consults"] += 1
        inputs = dict(inputs or {})
        cache_key = self._cache_key(spec_name, inputs)
        ttl_secs = self._resolve_ttl(ttl)

        cached = self._cache_get(cache_key, ttl_secs)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached

        self.stats["cache_misses"] += 1
        if not self.use_runtime:
            return None

        try:
            from aqp.agents.runtime import runtime_for
        except ImportError:
            logger.warning("AgentDispatcher: AgentRuntime is not available — returning None")
            return None

        try:
            result = runtime_for(spec_name).run(inputs)
        except Exception:
            self.stats["errors"] += 1
            logger.exception("AgentDispatcher: spec=%s failed", spec_name)
            return None
        self.stats["runtime_calls"] += 1
        self._cache_put(cache_key, result)
        return result

    async def consult_async(
        self,
        spec_name: str,
        inputs: Mapping[str, Any] | None = None,
        *,
        ttl: timedelta | float | None = None,
    ) -> Any:
        """Async variant — runs the sync call on a worker thread."""
        return await asyncio.to_thread(self.consult, spec_name, inputs, ttl=ttl)

    # ------------------------------------------------------------------
    # Cache plumbing
    # ------------------------------------------------------------------

    def _cache_key(self, spec_name: str, inputs: Mapping[str, Any]) -> str:
        return f"{spec_name}::{_stable_hash(inputs)}"

    def _resolve_ttl(self, ttl: timedelta | float | None) -> float | None:
        if ttl is None:
            return self.ttl_seconds
        if isinstance(ttl, timedelta):
            return ttl.total_seconds()
        return float(ttl)

    def _cache_get(self, key: str, ttl_seconds: float | None) -> Any:
        with self._lock:
            entry = self._lru.get(key)
            if entry is None:
                return None
            cached_at, value = entry
            if ttl_seconds is not None and (time.time() - cached_at) > ttl_seconds:
                del self._lru[key]
                return None
            self._lru.move_to_end(key)
            return value

    def _cache_put(self, key: str, value: Any) -> None:
        with self._lock:
            self._lru[key] = (time.time(), value)
            self._lru.move_to_end(key)
            while len(self._lru) > self.cache_size:
                self._lru.popitem(last=False)

    def reset(self) -> None:
        """Drop every cached entry (useful in tests)."""
        with self._lock:
            self._lru.clear()


def get_default_dispatcher() -> AgentDispatcher:
    """Lazy module-level singleton, mirroring :func:`runtime_for`'s ergonomics."""
    global _DEFAULT_DISPATCHER
    if _DEFAULT_DISPATCHER is None:
        _DEFAULT_DISPATCHER = AgentDispatcher()
    return _DEFAULT_DISPATCHER


_DEFAULT_DISPATCHER: AgentDispatcher | None = None


__all__ = ["AgentDispatcher", "get_default_dispatcher"]
