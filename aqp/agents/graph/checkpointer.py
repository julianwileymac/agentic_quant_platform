"""Redis-backed LangGraph checkpointer.

LangGraph's official ``BaseCheckpointSaver`` ships with SQLite + an
optional Redis adapter (``langgraph-checkpoint-redis``); this module
provides a minimal adapter that works with vanilla ``redis-py`` so we
don't pull in the extra package. When LangGraph isn't installed the
class still works as a plain ``KVCheckpointer`` for the
:class:`SequentialGraph` fallback.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)


class RedisCheckpointer:
    """Persist arbitrary thread state in Redis under ``aqp:graph:ckpt:*``."""

    def __init__(
        self,
        *,
        url: str | None = None,
        prefix: str = "aqp:graph:ckpt",
        ttl_seconds: int | None = 7 * 24 * 3600,
    ) -> None:
        self.url = url or settings.redis_url
        self.prefix = prefix
        self.ttl = ttl_seconds
        self._client = self._make_client()

    def _make_client(self):
        try:
            import redis  # type: ignore[import-not-found]

            client = redis.Redis.from_url(self.url, decode_responses=True)
            client.ping()
            return client
        except Exception:  # pragma: no cover
            logger.debug("Redis unavailable; checkpointer will no-op", exc_info=True)
            return None

    def _key(self, thread_id: str, step: int | str = "head") -> str:
        return f"{self.prefix}:{thread_id}:{step}"

    def save(self, thread_id: str, state: dict[str, Any], *, step: int | str = "head") -> None:
        if self._client is None or not thread_id:
            return
        try:
            payload = json.dumps(state, default=str)
            self._client.set(self._key(thread_id, step), payload, ex=self.ttl)
            self._client.set(self._key(thread_id, "head"), payload, ex=self.ttl)
        except Exception:  # pragma: no cover
            logger.debug("Checkpoint save failed", exc_info=True)

    def load(self, thread_id: str, *, step: int | str = "head") -> dict[str, Any] | None:
        if self._client is None or not thread_id:
            return None
        try:
            raw = self._client.get(self._key(thread_id, step))
            if not raw:
                return None
            return json.loads(raw)
        except Exception:  # pragma: no cover
            logger.debug("Checkpoint load failed", exc_info=True)
            return None

    def list_threads(self, limit: int = 100) -> list[str]:
        if self._client is None:
            return []
        try:
            cursor = 0
            seen: set[str] = set()
            while True:
                cursor, batch = self._client.scan(
                    cursor=cursor,
                    match=f"{self.prefix}:*:head",
                    count=200,
                )
                for key in batch:
                    if isinstance(key, bytes):
                        key = key.decode()
                    parts = key.split(":")
                    if len(parts) >= 3:
                        seen.add(parts[-2])
                    if len(seen) >= limit:
                        return sorted(seen)
                if cursor == 0:
                    break
            return sorted(seen)
        except Exception:  # pragma: no cover
            return []

    def delete(self, thread_id: str) -> int:
        if self._client is None:
            return 0
        try:
            cursor = 0
            n = 0
            while True:
                cursor, batch = self._client.scan(
                    cursor=cursor, match=f"{self.prefix}:{thread_id}:*", count=200
                )
                if batch:
                    self._client.delete(*batch)
                    n += len(batch)
                if cursor == 0:
                    break
            return n
        except Exception:  # pragma: no cover
            return 0


__all__ = ["RedisCheckpointer"]
