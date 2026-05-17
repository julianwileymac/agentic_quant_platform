"""Redis key/hash :class:`BaseDataset`.

Wraps a single Redis key (string / hash / json) so the discovery
browser can show "Redis-backed materialised feature snapshots" as
first-class catalog entries. The cache layer (:mod:`aqp.cache`) is
NOT this kind — these are *operator-visible* keys (e.g.
``aqp:features:current_universe``) that fall under business workflows
rather than the metadata prefetch.

Spec config schema::

    {
      "redis_url": "redis://localhost:6379/3",  # optional, default settings.redis_url
      "key": "aqp:features:universe",            # required
      "encoding": "string" | "hash" | "json",   # default "string"
    }
"""
from __future__ import annotations

import json
from typing import Any

from aqp.config import settings
from aqp.data.datasets.base import BaseDataset


class RedisKVDataset(BaseDataset):
    kind = "redis_kv"
    writable = True

    def _validate_spec(self) -> None:
        if not str(self._spec.config.get("key") or "").strip():
            raise ValueError("RedisKVDataset requires config.key")

    def _client(self) -> Any:
        try:
            import redis  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("redis-py is required for RedisKVDataset") from exc
        url = str(self._spec.config.get("redis_url") or settings.redis_url)
        return redis.Redis.from_url(url, decode_responses=True)

    @property
    def key(self) -> str:
        return str(self._spec.config["key"])

    @property
    def encoding(self) -> str:
        return str(self._spec.config.get("encoding") or "string").lower()

    def _load(self) -> Any:
        client = self._client()
        if self.encoding == "hash":
            return {str(k): str(v) for k, v in (client.hgetall(self.key) or {}).items()}
        value = client.get(self.key)
        if value is None:
            return None
        if self.encoding == "json":
            try:
                return json.loads(value)
            except Exception:  # noqa: BLE001
                return value
        return value

    def _save(self, payload: Any) -> Any:
        client = self._client()
        if self.encoding == "hash":
            if not isinstance(payload, dict):
                raise TypeError("hash encoding requires dict payload")
            client.hset(self.key, mapping={str(k): str(v) for k, v in payload.items()})
            return self.key
        if self.encoding == "json":
            client.set(self.key, json.dumps(payload, default=str))
            return self.key
        client.set(self.key, str(payload))
        return self.key

    def _exists(self) -> bool:
        return bool(self._client().exists(self.key))

    def _describe(self) -> dict[str, Any]:
        return {"key": self.key, "encoding": self.encoding, "load_mode": "redis_kv"}


__all__ = ["RedisKVDataset"]
