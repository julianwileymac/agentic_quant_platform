"""Redis 8 Stack vector store helpers.

Provides a RediSearch + RedisJSON backed vector store that mirrors the
API shape of `pipelines.vector_io.upsert_milvus` / `upsert_chromadb` and
`pipelines.retrieval.milvus_vector_search` / `chromadb_vector_search`.

Key conventions:

    * Every document key uses the `chunk:{collection}:{id}` keyspace so
      a single Redis can host many collections without FT.CREATE
      conflicts.
    * Vector fields default to HNSW + COSINE (robust for text embeddings
      and what the langgraph-redis/arxiv-paper-qa tutorials use).  FLAT
      + L2 is selectable via keyword args for smaller per-user indexes
      (semantic / episodic memory collections in agent_memory.py).
    * The vector dtype is FLOAT32 to match typical embedding providers;
      helpers below convert `list[float]` -> `bytes` transparently.

The module only imports `redis` lazily so importing this file in
environments without redis-py installed does not fail.
"""

from __future__ import annotations

import json
import logging
import struct
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .redis_io import get_redis, key, redis_span, require_modules

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _to_float32_bytes(vector: Sequence[float]) -> bytes:
    """Pack a vector as little-endian FLOAT32 bytes for RediSearch."""
    return struct.pack(f"<{len(vector)}f", *vector)


def _decode(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode()
        except UnicodeDecodeError:
            return value
    return value


@dataclass(slots=True)
class RedisVectorHit:
    """Single search hit."""

    id: str
    text: str
    score: float
    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------
def ensure_index(
    index_name: str,
    *,
    vector_dims: int,
    prefix: str | None = None,
    metric: str = "cosine",
    algorithm: str = "HNSW",
    text_fields: Sequence[str] = ("text",),
    tag_fields: Sequence[str] = ("source_key", "collection", "doc_id"),
    numeric_fields: Sequence[str] = ("chunk_index", "created_at"),
    client: Any | None = None,
    recreate: bool = False,
) -> str:
    """Create (or reuse) a RediSearch index backed by RedisJSON documents.

    Returns the index name actually used.  Idempotent unless
    ``recreate=True`` in which case ``FT.DROPINDEX ... DD`` is issued
    first (also deletes the underlying docs - dangerous).
    """
    require_modules(("search", "rejson"), client=client)
    client = client or get_redis()

    key_prefix = prefix or f"chunk:{index_name}:"

    if recreate:
        with redis_span("ft.dropindex", index=index_name):
            try:
                client.execute_command("FT.DROPINDEX", index_name, "DD")
            except Exception as exc:  # pragma: no cover
                logger.debug("FT.DROPINDEX %s skipped: %s", index_name, exc)

    try:
        with redis_span("ft.info", index=index_name):
            client.execute_command("FT.INFO", index_name)
        return index_name
    except Exception:
        pass  # falls through to create

    args: list[Any] = [
        "FT.CREATE",
        index_name,
        "ON", "JSON",
        "PREFIX", 1, key_prefix,
        "SCHEMA",
    ]
    for fname in text_fields:
        args.extend([f"$.{fname}", "AS", fname, "TEXT", "WEIGHT", 1.0])
    for fname in tag_fields:
        args.extend([f"$.metadata.{fname}", "AS", fname, "TAG", "SEPARATOR", "|"])
    for fname in numeric_fields:
        args.extend([f"$.metadata.{fname}", "AS", fname, "NUMERIC", "SORTABLE"])
    args.extend([
        "$.embedding", "AS", "embedding",
        "VECTOR", algorithm.upper(),
        12,  # param count for HNSW
        "TYPE", "FLOAT32",
        "DIM", int(vector_dims),
        "DISTANCE_METRIC", metric.upper(),
        "M", 16,
        "EF_CONSTRUCTION", 200,
        "EF_RUNTIME", 40,
    ])

    with redis_span("ft.create", index=index_name):
        client.execute_command(*args)

    logger.info(
        "Created RediSearch index %s (prefix=%s dim=%d metric=%s algorithm=%s)",
        index_name, key_prefix, vector_dims, metric, algorithm,
    )
    return index_name


def drop_index(index_name: str, *, delete_docs: bool = True, client: Any | None = None) -> None:
    """Drop a RediSearch index; optionally delete backing JSON docs."""
    client = client or get_redis()
    args = ["FT.DROPINDEX", index_name]
    if delete_docs:
        args.append("DD")
    with redis_span("ft.dropindex", index=index_name):
        try:
            client.execute_command(*args)
        except Exception as exc:  # pragma: no cover
            logger.debug("drop_index %s: %s", index_name, exc)


def index_info(index_name: str, *, client: Any | None = None) -> dict[str, Any]:
    """Return a normalized `FT.INFO` dict for *index_name* (empty on error)."""
    client = client or get_redis()
    try:
        with redis_span("ft.info", index=index_name):
            raw = client.execute_command("FT.INFO", index_name)
    except Exception:
        return {}
    info: dict[str, Any] = {}
    it = iter(raw)
    for k in it:
        v = next(it, None)
        info[_decode(k)] = _decode(v)
    return info


# ---------------------------------------------------------------------------
# Upsert + query
# ---------------------------------------------------------------------------
def upsert_chunks(
    index_name: str,
    records: list[dict[str, Any]],
    *,
    prefix: str | None = None,
    client: Any | None = None,
) -> int:
    """Upsert RAG chunk records into Redis.

    Each record must include ``id``, ``text``, and ``embedding`` (a
    sequence of floats).  Extra keys under ``metadata`` are indexed if
    they match the field list in ``ensure_index``.
    """
    if not records:
        return 0

    client = client or get_redis()
    key_prefix = prefix or f"chunk:{index_name}:"

    with redis_span("json.mset", index=index_name, count=len(records)):
        pipe = client.pipeline(transaction=False)
        for rec in records:
            rid = str(rec.get("id") or uuid.uuid4())
            payload = {
                "id": rid,
                "text": rec.get("text", ""),
                "embedding": list(rec.get("embedding", [])),
                "metadata": rec.get("metadata", {}),
            }
            pipe.execute_command(
                "JSON.SET", f"{key_prefix}{rid}", "$", json.dumps(payload)
            )
        pipe.execute()

    return len(records)


def vector_search(
    index_name: str,
    query_vector: Sequence[float],
    *,
    top_k: int = 10,
    filters: str | None = None,
    return_fields: Sequence[str] = ("text", "metadata"),
    client: Any | None = None,
) -> list[RedisVectorHit]:
    """KNN vector search against a RediSearch index.

    ``filters`` is a pre-query expression in RediSearch syntax (e.g.
    ``@collection:{docs} @chunk_index:[0 100]``).  Pass ``None`` for no
    filter.  The KNN post-filter is always appended.
    """
    client = client or get_redis()
    prefilter = filters.strip() if filters else "*"
    qstr = f"({prefilter})=>[KNN {top_k} @embedding $BLOB AS vector_score]"

    args: list[Any] = [
        "FT.SEARCH",
        index_name,
        qstr,
        "PARAMS", 2, "BLOB", _to_float32_bytes(query_vector),
        "SORTBY", "vector_score",
        "RETURN", len(return_fields) + 1, "vector_score", *return_fields,
        "DIALECT", 2,
        "LIMIT", 0, top_k,
    ]

    with redis_span("ft.search", index=index_name, top_k=top_k):
        raw = client.execute_command(*args)

    return _parse_search_results(raw, return_fields)


def _parse_search_results(
    raw: Any,
    return_fields: Sequence[str],
) -> list[RedisVectorHit]:
    if not raw or not isinstance(raw, list):
        return []
    hits: list[RedisVectorHit] = []
    iterator = iter(raw[1:])
    for redis_key in iterator:
        fields = next(iterator, None)
        if fields is None:
            break
        data: dict[str, Any] = {}
        it = iter(fields)
        for k in it:
            v = next(it, None)
            data[_decode(k)] = _decode(v)
        score = float(data.pop("vector_score", 0.0) or 0.0)
        text_val = data.pop("text", "") or ""
        meta_val = data.pop("metadata", None)
        metadata: dict[str, Any]
        if isinstance(meta_val, str):
            try:
                metadata = json.loads(meta_val)
            except json.JSONDecodeError:
                metadata = {"raw": meta_val}
        elif isinstance(meta_val, dict):
            metadata = meta_val
        else:
            metadata = {k: data[k] for k in list(data)}
        # Carry remaining fields into metadata for callers that requested
        # them via return_fields.
        for rf in return_fields:
            if rf not in ("text", "metadata") and rf in data:
                metadata.setdefault(rf, data[rf])
        hits.append(
            RedisVectorHit(
                id=_decode(redis_key).split(":", 2)[-1],
                text=text_val,
                score=score,
                metadata=metadata,
            )
        )
    return hits


def keyword_search(
    index_name: str,
    query: str,
    *,
    top_k: int = 10,
    return_fields: Sequence[str] = ("text", "metadata"),
    client: Any | None = None,
) -> list[RedisVectorHit]:
    """Plain RediSearch full-text query without a vector clause."""
    client = client or get_redis()
    args: list[Any] = [
        "FT.SEARCH",
        index_name,
        query or "*",
        "RETURN", len(return_fields), *return_fields,
        "LIMIT", 0, top_k,
        "DIALECT", 2,
    ]
    with redis_span("ft.search", index=index_name, mode="keyword"):
        raw = client.execute_command(*args)
    return _parse_search_results(raw, return_fields)


def delete_document(
    index_name: str,
    doc_id: str,
    *,
    prefix: str | None = None,
    client: Any | None = None,
) -> int:
    """Delete a single chunk document by id.  Returns 1 if removed."""
    client = client or get_redis()
    key_prefix = prefix or f"chunk:{index_name}:"
    with redis_span("json.del", index=index_name):
        return int(client.delete(f"{key_prefix}{doc_id}"))


def delete_by_filter(
    index_name: str,
    filters: str,
    *,
    client: Any | None = None,
    batch: int = 256,
) -> int:
    """Delete every indexed doc matching *filters* (RediSearch query)."""
    client = client or get_redis()
    removed = 0
    cursor = 0
    while True:
        with redis_span("ft.search", index=index_name, mode="delete"):
            raw = client.execute_command(
                "FT.SEARCH",
                index_name,
                filters,
                "NOCONTENT",
                "LIMIT", cursor, batch,
                "DIALECT", 2,
            )
        if not raw or len(raw) <= 1:
            break
        ids = [_decode(k) for k in raw[1:]]
        if not ids:
            break
        removed += int(client.delete(*ids))
        if len(ids) < batch:
            break
        cursor += batch
    return removed


__all__ = [
    "RedisVectorHit",
    "delete_by_filter",
    "delete_document",
    "drop_index",
    "ensure_index",
    "index_info",
    "keyword_search",
    "upsert_chunks",
    "vector_search",
]
