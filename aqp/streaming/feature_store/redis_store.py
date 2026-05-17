"""``RedisFeatureStore`` — Redis-backed implementation of :class:`IFeatureStore`.

The Flink topology writes feature payloads into the canonical
``aqp:features:{feature_set}:{vt_symbol}:{epoch_ts_ms}`` keyspace
(integer epoch ms suffix sorted lex). The RL paper-trading loop
reads them via this store so the live observation matches the
offline Iceberg-backed observation byte-for-byte.

The store is reserved for Flink-produced feature payloads. It does
NOT participate in the metadata cache (``aqp:cache:*``) or the
Dagster sandbox (``aqp:sandbox:*``) namespaces (AGENTS.md rule 32 +
the data-discovery contract).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_FEATURE_PREFIX = "aqp:features"


def _epoch_ms(timestamp: datetime) -> int:
    if hasattr(timestamp, "timestamp"):
        return int(timestamp.timestamp() * 1000)
    return int(datetime.utcnow().timestamp() * 1000)


def _feature_key(feature_set: str, vt_symbol: str, epoch_ms: int) -> str:
    return f"{_FEATURE_PREFIX}:{feature_set}:{vt_symbol}:{epoch_ms}"


def _feature_pattern(feature_set: str, vt_symbol: str) -> str:
    return f"{_FEATURE_PREFIX}:{feature_set}:{vt_symbol}:*"


class RedisFeatureStore:
    """Redis-backed implementation of :class:`aqp.core.interfaces.IFeatureStore`.

    Parameters
    ----------
    redis_client:
        Optional explicit ``redis.Redis`` client (useful for tests
        with ``fakeredis``). Defaults to constructing from
        ``settings.redis_url``.
    ttl_seconds:
        Optional TTL for feature payloads — the Flink writer should
        also stamp the TTL but we accept it here as a safety net. A
        ``None`` value leaves keys long-lived (the Flink topology
        retention policy then becomes the authority).
    """

    def __init__(
        self,
        *,
        redis_client: Any | None = None,
        ttl_seconds: int | None = 24 * 3600,
    ) -> None:
        self._client = redis_client
        self.ttl_seconds = int(ttl_seconds) if ttl_seconds is not None else None

    # ------------------------------------------------------------------ IFeatureStore

    def get_features(
        self,
        symbol: Any,
        timestamp: datetime,
        feature_set: str,
    ) -> dict[str, float]:
        """Return the latest features for ``(symbol, feature_set)`` at-or-before ``timestamp``.

        Picks the most recent key in the keyspace whose epoch-ms
        suffix is at-or-before the requested ``timestamp`` — defeats
        lookahead bias when the loop is replayed deterministically.
        """
        vt_symbol = self._coerce_vt_symbol(symbol)
        epoch_ms = _epoch_ms(timestamp)
        client = self._resolve_client()
        if client is None:
            return {}
        pattern = _feature_pattern(feature_set, vt_symbol)
        try:
            keys = sorted(client.scan_iter(match=pattern))
        except Exception:
            logger.exception("RedisFeatureStore: scan failed for %s", pattern)
            return {}
        target_key: str | None = None
        for key in keys:
            try:
                key_epoch = int(str(key).rsplit(":", 1)[-1])
            except Exception:
                continue
            if key_epoch <= epoch_ms:
                target_key = key if isinstance(key, str) else key.decode()
        if target_key is None:
            return {}
        try:
            raw = client.get(target_key)
        except Exception:
            logger.exception("RedisFeatureStore: get(%s) failed", target_key)
            return {}
        if raw is None:
            return {}
        try:
            return self._decode_payload(raw)
        except Exception:
            logger.exception("RedisFeatureStore: decode(%s) failed", target_key)
            return {}

    # ------------------------------------------------------------------ writers (Flink-side)

    def write_features(
        self,
        symbol: Any,
        timestamp: datetime,
        feature_set: str,
        features: dict[str, float],
    ) -> str:
        """Write a feature payload — called by the Flink topology only.

        Producer-side helper kept here so the keyspace contract has a
        single canonical encoding. RL training / paper code MUST NOT
        call this — only the Flink sink does.
        """
        vt_symbol = self._coerce_vt_symbol(symbol)
        epoch_ms = _epoch_ms(timestamp)
        key = _feature_key(feature_set, vt_symbol, epoch_ms)
        client = self._resolve_client()
        if client is None:
            return key
        payload = json.dumps({k: float(v) for k, v in features.items()}, separators=(",", ":"))
        try:
            if self.ttl_seconds:
                client.setex(key, self.ttl_seconds, payload)
            else:
                client.set(key, payload)
        except Exception:
            logger.exception("RedisFeatureStore: write(%s) failed", key)
        return key

    # ------------------------------------------------------------------ helpers

    def _coerce_vt_symbol(self, symbol: Any) -> str:
        if hasattr(symbol, "vt_symbol"):
            return str(symbol.vt_symbol)
        return str(symbol)

    def _decode_payload(self, raw: Any) -> dict[str, float]:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            return {}
        try:
            obj = json.loads(raw)
        except Exception:
            return {}
        if not isinstance(obj, dict):
            return {}
        out: dict[str, float] = {}
        for k, v in obj.items():
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        return out

    def _resolve_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        try:
            import redis

            from aqp.config import settings

            self._client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            return self._client
        except Exception:
            logger.debug("RedisFeatureStore: redis unavailable; degrading to no-op", exc_info=True)
            return None


__all__ = ["RedisFeatureStore"]
