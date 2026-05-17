"""Real-time feature store backing :class:`IFeatureStore`.

The Phase 5 RL paper-trading loop reads per-bar feature vectors out
of this store so the live RL state observation matches the offline
Iceberg-backed observation byte-for-byte. The Flink topology in
``aqp/streaming/`` writes feature payloads into the canonical
``aqp:features:{feature_set}:{vt_symbol}:{epoch_ts}`` keyspace; the
:class:`RedisFeatureStore` reads them.

Determinism contract
--------------------

The store is read-only from the consumer's perspective. The Flink
writer is the single producer; the keyspace MUST stay
``aqp:features:*`` — clashes with other keys silently corrupt the
observation distribution.
"""
from __future__ import annotations

from aqp.streaming.feature_store.redis_store import RedisFeatureStore

__all__ = ["RedisFeatureStore"]
