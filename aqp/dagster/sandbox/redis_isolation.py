"""Per-session Redis namespacing for the Dagster sandbox.

Reuses Phase 0's :class:`aqp.cache.MetadataCache` but every key the
sandbox writes lives under ``aqp:sandbox:<session_id>:*``. The
production cache + RAG indexes never see sandbox writes; tearing
down a session is a single ``KEYS aqp:sandbox:<id>:*`` + ``DEL``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from aqp.cache.client import MetadataCache, get_cache

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SandboxRedisNamespace:
    """Wrap a :class:`MetadataCache` to enforce a session prefix."""

    session_id: str
    cache: MetadataCache

    @property
    def prefix(self) -> str:
        return f"aqp:sandbox:{self.session_id}"

    def key(self, suffix: str) -> str:
        return f"{self.prefix}:{suffix.lstrip(':')}"

    def set(self, suffix: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.cache.set_string(self.key(suffix), value, ttl_seconds=ttl_seconds)

    def get(self, suffix: str) -> str | None:
        return self.cache.get_string(self.key(suffix))

    def teardown(self) -> int:
        """Delete every key under the session prefix. Returns count."""
        try:
            keys = self.cache.keys(f"{self.prefix}:*")
        except Exception:  # noqa: BLE001
            return 0
        if not keys:
            return 0
        return self.cache.delete(*keys)


def make_namespace(session_id: str) -> SandboxRedisNamespace:
    return SandboxRedisNamespace(session_id=session_id, cache=get_cache())


__all__ = ["SandboxRedisNamespace", "make_namespace"]
