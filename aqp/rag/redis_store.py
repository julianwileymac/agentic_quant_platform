"""Redis-backed vector store using RediSearch HNSW indexes.

Single Redis instance (``settings.redis_url``) is used for vector search,
hybrid tag filters (level / order / corpus / vt_symbol / as_of), and as a
content-addressed cache for ``(corpus, source_id, chunk_idx)``.

Index layout per corpus + level:

- Hash key: ``{prefix}:{corpus}:{level}:{doc_id}``
- Hash fields:
    - ``vector``     — float32 little-endian byte blob (length = ``dim * 4``)
    - ``text``       — chunk text
    - ``corpus``     — corpus slug (TAG)
    - ``order``      — first | second | third (TAG)
    - ``level``      — l0 | l1 | l2 | l3 (TAG)
    - ``l1`` / ``l2`` — taxonomy slugs (TAG)
    - ``vt_symbol``  — instrument symbol (TAG, optional)
    - ``as_of``      — ISO date (TAG, optional)
    - ``source_id``  — upstream record id (TEXT)
    - ``chunk_idx``  — 0-based chunk index (NUMERIC)
    - ``meta``       — JSON-encoded extras (TEXT)

In-memory fallback: when ``redis`` / RediSearch isn't available, we
keep a process-local ``InMemoryVectorIndex`` so unit tests and the
in-process dev loop work without a server.
"""
from __future__ import annotations

import json
import logging
import struct
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from aqp.config import settings
from aqp.rag.embedder import get_embedder

logger = logging.getLogger(__name__)


VALID_LEVELS: tuple[str, ...] = ("l0", "l1", "l2", "l3")


def _float_blob(vec: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *map(float, vec))


def _decode_blob(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    s = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=False):
        s += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return s / ((na**0.5) * (nb**0.5))


@dataclass
class VectorRecord:
    """Stored chunk with metadata."""

    doc_id: str
    text: str
    corpus: str
    level: str
    order: str
    l1: str = ""
    l2: str = ""
    vt_symbol: str = ""
    as_of: str = ""
    source_id: str = ""
    chunk_idx: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    def fields(self, vector: Sequence[float]) -> dict[str, Any]:
        return {
            "vector": _float_blob(vector),
            "text": self.text,
            "corpus": self.corpus,
            "level": self.level,
            "order": self.order,
            "l1": self.l1,
            "l2": self.l2,
            "vt_symbol": self.vt_symbol,
            "as_of": self.as_of,
            "source_id": self.source_id,
            "chunk_idx": int(self.chunk_idx),
            "meta": json.dumps(self.meta or {}, default=str),
        }


@dataclass
class VectorHit:
    """One ranked search result."""

    doc_id: str
    score: float
    text: str
    corpus: str
    level: str
    order: str
    l1: str = ""
    l2: str = ""
    vt_symbol: str = ""
    as_of: str = ""
    source_id: str = ""
    chunk_idx: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


class _InMemoryVectorIndex:
    """Tiny brute-force fallback used when Redis Stack isn't reachable."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # Indexed by (corpus, level) -> {doc_id: (vector, record)}
        self._store: dict[tuple[str, str], dict[str, tuple[list[float], VectorRecord]]] = {}

    def upsert(
        self,
        records: Iterable[tuple[VectorRecord, Sequence[float]]],
    ) -> int:
        n = 0
        with self._lock:
            for rec, vec in records:
                key = (rec.corpus, rec.level)
                bucket = self._store.setdefault(key, {})
                bucket[rec.doc_id] = (list(map(float, vec)), rec)
                n += 1
        return n

    def search(
        self,
        vector: Sequence[float],
        *,
        k: int,
        corpus: str | None = None,
        level: str | None = None,
        order: str | None = None,
        l1: str | None = None,
        l2: str | None = None,
        vt_symbol: str | None = None,
        as_of_prefix: str | None = None,
    ) -> list[VectorHit]:
        with self._lock:
            buckets: list[dict[str, tuple[list[float], VectorRecord]]] = []
            for (c, lv), bucket in self._store.items():
                if corpus and c != corpus:
                    continue
                if level and lv != level:
                    continue
                buckets.append(bucket)
            scored: list[tuple[float, VectorRecord]] = []
            for bucket in buckets:
                for vec, rec in bucket.values():
                    if order and rec.order != order:
                        continue
                    if l1 and rec.l1 != l1:
                        continue
                    if l2 and rec.l2 != l2:
                        continue
                    if vt_symbol and rec.vt_symbol != vt_symbol:
                        continue
                    if as_of_prefix and not rec.as_of.startswith(as_of_prefix):
                        continue
                    scored.append((_cosine(vector, vec), rec))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [
                VectorHit(
                    doc_id=rec.doc_id,
                    score=float(score),
                    text=rec.text,
                    corpus=rec.corpus,
                    level=rec.level,
                    order=rec.order,
                    l1=rec.l1,
                    l2=rec.l2,
                    vt_symbol=rec.vt_symbol,
                    as_of=rec.as_of,
                    source_id=rec.source_id,
                    chunk_idx=rec.chunk_idx,
                    meta=rec.meta,
                )
                for score, rec in scored[:k]
            ]

    def delete_corpus(self, corpus: str) -> int:
        n = 0
        with self._lock:
            for key in list(self._store):
                if key[0] == corpus:
                    n += len(self._store.pop(key))
        return n

    def count(self, corpus: str | None = None, level: str | None = None) -> int:
        with self._lock:
            total = 0
            for (c, lv), bucket in self._store.items():
                if corpus and c != corpus:
                    continue
                if level and lv != level:
                    continue
                total += len(bucket)
            return total


class RedisVectorStore:
    """Vector + tag store backed by Redis Stack (RediSearch).

    Falls back to a process-local in-memory index when:

    - The ``redis`` Python package isn't installed, OR
    - The configured Redis can't be reached, OR
    - The server doesn't expose RediSearch (no ``FT.CREATE``).

    The fallback supports the same API surface (with degraded performance
    and per-process scope) so unit tests and developer loops never hard
    fail on missing infrastructure.
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        prefix: str | None = None,
        embed_dim: int | None = None,
    ) -> None:
        self.url = url or settings.redis_url
        self.prefix = prefix or getattr(settings, "rag_redis_prefix", "aqp:rag")
        self._dim = int(embed_dim or get_embedder().dim)
        self._client = self._make_client()
        self._mem: _InMemoryVectorIndex | None = None
        if self._client is None:
            self._mem = _InMemoryVectorIndex()
        self._ensured_indexes: set[tuple[str, str]] = set()

    # ------------------------------------------------------------------ client setup
    def _make_client(self):
        try:
            import redis  # type: ignore[import-not-found]
        except Exception:  # pragma: no cover
            logger.warning("redis-py not installed; using in-memory fallback for RAG.")
            return None
        try:
            client = redis.Redis.from_url(self.url, decode_responses=False)
            client.ping()
            return client
        except Exception:  # noqa: BLE001
            logger.warning(
                "Redis at %s unreachable; using in-memory fallback for RAG.",
                self.url,
            )
            return None

    # ------------------------------------------------------------------ indexes
    def _index_name(self, corpus: str, level: str) -> str:
        return f"{self.prefix}:idx:{corpus}:{level}"

    def _key_prefix(self, corpus: str, level: str) -> str:
        return f"{self.prefix}:{corpus}:{level}:"

    def _doc_key(self, corpus: str, level: str, doc_id: str) -> str:
        return f"{self._key_prefix(corpus, level)}{doc_id}"

    def _ensure_index(self, corpus: str, level: str) -> bool:
        if self._client is None:
            return False
        if (corpus, level) in self._ensured_indexes:
            return True
        try:
            from redis.commands.search.field import (  # type: ignore[import-not-found]
                NumericField,
                TagField,
                TextField,
                VectorField,
            )
            from redis.commands.search.indexDefinition import (  # type: ignore[import-not-found]
                IndexDefinition,
                IndexType,
            )
        except Exception:  # pragma: no cover
            logger.warning("RediSearch not available on this redis-py; using fallback.")
            self._client = None
            self._mem = _InMemoryVectorIndex()
            return False

        idx_name = self._index_name(corpus, level)
        try:
            self._client.ft(idx_name).info()
            self._ensured_indexes.add((corpus, level))
            return True
        except Exception:
            pass

        schema = (
            VectorField(
                "vector",
                "HNSW",
                {
                    "TYPE": "FLOAT32",
                    "DIM": self._dim,
                    "DISTANCE_METRIC": "COSINE",
                    "M": 16,
                    "EF_CONSTRUCTION": 200,
                },
            ),
            TextField("text"),
            TagField("corpus"),
            TagField("order"),
            TagField("level"),
            TagField("l1"),
            TagField("l2"),
            TagField("vt_symbol"),
            TagField("as_of"),
            TextField("source_id"),
            NumericField("chunk_idx"),
            TextField("meta"),
        )
        definition = IndexDefinition(
            prefix=[self._key_prefix(corpus, level)],
            index_type=IndexType.HASH,
        )
        try:
            self._client.ft(idx_name).create_index(schema, definition=definition)
            self._ensured_indexes.add((corpus, level))
            logger.info("Created RediSearch index %s (dim=%d)", idx_name, self._dim)
            return True
        except Exception:  # noqa: BLE001
            logger.warning(
                "Could not create RediSearch index %s; switching to in-memory fallback.",
                idx_name,
                exc_info=True,
            )
            self._client = None
            self._mem = _InMemoryVectorIndex()
            return False

    # ------------------------------------------------------------------ writes
    def upsert(
        self,
        records: Iterable[tuple[VectorRecord, Sequence[float]]],
    ) -> int:
        items = list(records)
        if not items:
            return 0
        first_level = items[0][0].level
        first_corpus = items[0][0].corpus
        if self._client is None or not self._ensure_index(first_corpus, first_level):
            assert self._mem is not None
            return self._mem.upsert(items)
        pipe = self._client.pipeline(transaction=False)
        for rec, vec in items:
            if len(vec) != self._dim:
                raise ValueError(
                    f"Vector dim mismatch: got {len(vec)}, expected {self._dim} for record {rec.doc_id!r}"
                )
            self._ensure_index(rec.corpus, rec.level)
            key = self._doc_key(rec.corpus, rec.level, rec.doc_id)
            pipe.hset(key, mapping=rec.fields(vec))
        pipe.execute()
        return len(items)

    def delete_corpus(self, corpus: str) -> int:
        if self._client is None:
            assert self._mem is not None
            return self._mem.delete_corpus(corpus)
        n = 0
        for level in VALID_LEVELS:
            cursor = 0
            pat = f"{self._key_prefix(corpus, level)}*"
            while True:
                cursor, batch = self._client.scan(cursor=cursor, match=pat, count=500)
                if batch:
                    self._client.delete(*batch)
                    n += len(batch)
                if cursor == 0:
                    break
        return n

    # ------------------------------------------------------------------ reads
    def count(self, corpus: str | None = None, level: str | None = None) -> int:
        if self._client is None:
            assert self._mem is not None
            return self._mem.count(corpus=corpus, level=level)
        n = 0
        levels = (level,) if level else VALID_LEVELS
        corpora_iter: Iterable[str | None] = (corpus,) if corpus else (None,)
        for c in corpora_iter:
            for lv in levels:
                pat = (
                    f"{self._key_prefix(c, lv)}*"
                    if c
                    else f"{self.prefix}:*:{lv}:*"
                )
                cursor = 0
                while True:
                    cursor, batch = self._client.scan(cursor=cursor, match=pat, count=500)
                    n += len(batch)
                    if cursor == 0:
                        break
        return n

    def search(
        self,
        vector: Sequence[float],
        *,
        k: int = 10,
        corpus: str | None = None,
        level: str | None = None,
        order: str | None = None,
        l1: str | None = None,
        l2: str | None = None,
        vt_symbol: str | None = None,
        as_of_prefix: str | None = None,
    ) -> list[VectorHit]:
        if self._client is None or not corpus or not level:
            # Fallback path or unfiltered scan needs the in-memory store;
            # callers should always pass corpus + level for Redis.
            if self._mem is not None:
                return self._mem.search(
                    vector,
                    k=k,
                    corpus=corpus,
                    level=level,
                    order=order,
                    l1=l1,
                    l2=l2,
                    vt_symbol=vt_symbol,
                    as_of_prefix=as_of_prefix,
                )
            if not corpus or not level:
                raise ValueError(
                    "Redis path requires both corpus and level filters; in-memory fallback unavailable."
                )
            return []
        if not self._ensure_index(corpus, level):
            assert self._mem is not None
            return self._mem.search(
                vector,
                k=k,
                corpus=corpus,
                level=level,
                order=order,
                l1=l1,
                l2=l2,
                vt_symbol=vt_symbol,
                as_of_prefix=as_of_prefix,
            )
        try:
            from redis.commands.search.query import Query  # type: ignore[import-not-found]
        except Exception:  # pragma: no cover
            return []

        filters: list[str] = []
        if order:
            filters.append(f"@order:{{{order}}}")
        if l1:
            filters.append(f"@l1:{{{l1}}}")
        if l2:
            filters.append(f"@l2:{{{l2}}}")
        if vt_symbol:
            filters.append(f"@vt_symbol:{{{_escape_tag(vt_symbol)}}}")
        if as_of_prefix:
            filters.append(f"@as_of:{{{_escape_tag(as_of_prefix)}*}}")
        prefilter = " ".join(filters) if filters else "*"
        query_str = f"({prefilter})=>[KNN {int(k)} @vector $vec AS score]"
        q = (
            Query(query_str)
            .sort_by("score")
            .return_fields(
                "score",
                "text",
                "corpus",
                "level",
                "order",
                "l1",
                "l2",
                "vt_symbol",
                "as_of",
                "source_id",
                "chunk_idx",
                "meta",
            )
            .dialect(2)
            .paging(0, int(k))
        )
        try:
            res = self._client.ft(self._index_name(corpus, level)).search(
                q, query_params={"vec": _float_blob(vector)}
            )
        except Exception:  # noqa: BLE001
            logger.exception("RediSearch query failed; returning empty result.")
            return []
        out: list[VectorHit] = []
        for doc in res.docs:
            try:
                meta = json.loads(getattr(doc, "meta", "") or "{}")
            except Exception:
                meta = {}
            out.append(
                VectorHit(
                    doc_id=str(doc.id).split(":", 3)[-1],
                    score=1.0 - float(getattr(doc, "score", 0.0)),
                    text=str(getattr(doc, "text", "")),
                    corpus=str(getattr(doc, "corpus", "")),
                    level=str(getattr(doc, "level", "")),
                    order=str(getattr(doc, "order", "")),
                    l1=str(getattr(doc, "l1", "") or ""),
                    l2=str(getattr(doc, "l2", "") or ""),
                    vt_symbol=str(getattr(doc, "vt_symbol", "") or ""),
                    as_of=str(getattr(doc, "as_of", "") or ""),
                    source_id=str(getattr(doc, "source_id", "") or ""),
                    chunk_idx=int(float(getattr(doc, "chunk_idx", 0) or 0)),
                    meta=meta,
                )
            )
        return out

    # ------------------------------------------------------------------ small helpers used by HierarchicalRAG
    def get(self, corpus: str, level: str, doc_id: str) -> VectorHit | None:
        if self._client is None:
            assert self._mem is not None
            bucket = self._mem._store.get((corpus, level), {})
            entry = bucket.get(doc_id)
            if entry is None:
                return None
            _, rec = entry
            return VectorHit(
                doc_id=rec.doc_id,
                score=1.0,
                text=rec.text,
                corpus=rec.corpus,
                level=rec.level,
                order=rec.order,
                l1=rec.l1,
                l2=rec.l2,
                vt_symbol=rec.vt_symbol,
                as_of=rec.as_of,
                source_id=rec.source_id,
                chunk_idx=rec.chunk_idx,
                meta=rec.meta,
            )
        key = self._doc_key(corpus, level, doc_id)
        try:
            payload = self._client.hgetall(key)
        except Exception:  # noqa: BLE001
            return None
        if not payload:
            return None
        decoded: Mapping[str, Any] = {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) and k != b"vector" else v)
            for k, v in payload.items()
        }
        try:
            meta = json.loads(decoded.get("meta", "") or "{}")
        except Exception:
            meta = {}
        return VectorHit(
            doc_id=doc_id,
            score=1.0,
            text=str(decoded.get("text", "")),
            corpus=str(decoded.get("corpus", "")),
            level=str(decoded.get("level", "")),
            order=str(decoded.get("order", "")),
            l1=str(decoded.get("l1", "") or ""),
            l2=str(decoded.get("l2", "") or ""),
            vt_symbol=str(decoded.get("vt_symbol", "") or ""),
            as_of=str(decoded.get("as_of", "") or ""),
            source_id=str(decoded.get("source_id", "") or ""),
            chunk_idx=int(float(decoded.get("chunk_idx", 0) or 0)),
            meta=meta,
        )


def _escape_tag(value: str) -> str:
    """Escape special characters so RediSearch tag filters parse cleanly."""
    return (
        value.replace("\\", "\\\\")
        .replace("-", "\\-")
        .replace(":", "\\:")
        .replace(".", "\\.")
        .replace("/", "\\/")
        .replace("@", "\\@")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace(" ", "\\ ")
    )


__all__ = [
    "RedisVectorStore",
    "VALID_LEVELS",
    "VectorHit",
    "VectorRecord",
]
