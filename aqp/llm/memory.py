"""Hybrid agent memory — BM25 + Chroma + Redis hierarchical RAG.

Three layered backends:

- :class:`BM25Memory` — cheap, offline, per-role memory with outcome-based recall.
- :class:`HybridMemory` — BM25 + ChromaDB (legacy hybrid, kept for parity).
- :class:`RedisHybridMemory` — BM25 + Redis (working) + Hierarchical RAG L0
  (episodic / reflection). This is the binding the new ``AgentRuntime``
  uses by default; it falls back to the BM25 + Chroma path whenever
  Redis or the RAG hierarchy isn't reachable.

Inspired by TradingAgents' ``FinancialSituationMemory``: lexical BM25
avoids per-reflection embedding cost for the high-volume trade-outcome
feedback loop, while RediSearch / ChromaDB handle the slower-changing
research corpus.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from aqp.config import settings

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    id: str
    role: str
    situation: str
    lesson: str
    outcome: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def tokenise(self) -> list[str]:
        return (self.situation + " " + self.lesson).lower().split()


class BM25Memory:
    """Cheap, offline, per-role memory with outcome-based retrieval."""

    def __init__(self, role: str, persist_dir: Path | None = None) -> None:
        self.role = role
        self.persist_dir = Path(persist_dir or (settings.data_dir / "memory"))
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._path = self.persist_dir / f"{role}.jsonl"
        self._entries: list[MemoryEntry] = self._load()
        self._index: BM25Okapi | None = None
        self._rebuild_index()

    # --- persistence ----
    def _load(self) -> list[MemoryEntry]:
        if not self._path.exists():
            return []
        entries: list[MemoryEntry] = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    entries.append(MemoryEntry(**d))
                except Exception:  # pragma: no cover
                    logger.exception("Malformed memory row")
        return entries

    def _persist(self, entry: MemoryEntry) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.__dict__) + "\n")

    def _rebuild_index(self) -> None:
        if not self._entries:
            self._index = None
            return
        corpus = [e.tokenise() for e in self._entries]
        self._index = BM25Okapi(corpus)

    # --- public API ----
    def add(
        self,
        situation: str,
        lesson: str,
        outcome: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            role=self.role,
            situation=situation,
            lesson=lesson,
            outcome=outcome,
            metadata=metadata or {},
        )
        self._entries.append(entry)
        self._persist(entry)
        self._rebuild_index()
        return entry.id

    def recall(self, query: str, k: int = 3) -> list[MemoryEntry]:
        if not self._entries or self._index is None:
            return []
        scores = self._index.get_scores(query.lower().split())
        ranked = sorted(
            zip(scores, self._entries, strict=False),
            key=lambda x: x[0],
            reverse=True,
        )
        return [e for _, e in ranked[:k]]

    def __len__(self) -> int:
        return len(self._entries)


class HybridMemory:
    """Combines per-role BM25 with a global ChromaDB memory collection."""

    def __init__(self, role: str) -> None:
        self.role = role
        self.bm25 = BM25Memory(role)
        self._chroma = None

    @property
    def chroma(self):
        if self._chroma is None:
            from aqp.data.chroma_store import ChromaStore

            self._chroma = ChromaStore()
        return self._chroma

    def reflect(
        self,
        situation: str,
        lesson: str,
        outcome: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.bm25.add(situation, lesson, outcome, metadata)
        text = f"Situation: {situation}\nLesson: {lesson}"
        try:
            self.chroma.remember(text, role=self.role, tags=[self.role], extra=metadata or {})
        except Exception:  # pragma: no cover
            logger.exception("Chroma remember failed; BM25 saved OK")

    def recall(self, query: str, k: int = 3) -> list[str]:
        bm25_hits = [f"[BM25/{e.role}] {e.lesson}" for e in self.bm25.recall(query, k)]
        try:
            chroma_hits = [f"[Chroma] {h['document']}" for h in self.chroma.recall(query, k, role=self.role)]
        except Exception:  # pragma: no cover
            chroma_hits = []
        return bm25_hits + chroma_hits


class RedisHybridMemory:
    """Per-role memory backed by Redis (working / reflections) + BM25 + RAG L0.

    Three logical layers (matching the agent runtime contract):

    - **working** — short-lived per-run context kept in a Redis list; gives
      the LLM access to its own most recent observations within a single
      agent run. Trimmed to ``working_max`` entries.
    - **episodic** — durable per-role recollections (situation + lesson +
      outcome). Always written to BM25 for lexical recall and to the
      :class:`HierarchicalRAG` ``decisions`` corpus for semantic recall
      across the platform (paper RAG#0 alpha base).
    - **reflection** — post-outcome lessons fed back into the L0 alpha
      base and surfaced to the next run via :meth:`recall_reflections`
      (TradingAgents-style deferred outcome reflection).

    Falls back to BM25 + the existing ``ChromaStore`` whenever Redis or
    the RAG hierarchy isn't reachable, so behaviour stays identical for
    environments that haven't switched on Redis Stack yet.
    """

    def __init__(
        self,
        role: str,
        *,
        working_max: int = 64,
        rag=None,
    ) -> None:
        self.role = role
        self.bm25 = BM25Memory(role)
        self.working_max = max(1, int(working_max))
        self._rag = rag
        self._redis = self._make_redis()

    # ------------------------------------------------------------------ wiring
    def _make_redis(self):
        try:
            import redis  # type: ignore[import-not-found]

            client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            client.ping()
            return client
        except Exception:  # pragma: no cover
            logger.debug("Redis unavailable for memory; using in-process fallback.", exc_info=True)
            return None

    @property
    def rag(self):
        if self._rag is not None:
            return self._rag
        try:
            from aqp.rag import get_default_rag

            self._rag = get_default_rag()
        except Exception:  # pragma: no cover
            self._rag = None
        return self._rag

    # ------------------------------------------------------------------ keys
    def _working_key(self, run_id: str) -> str:
        return f"aqp:mem:work:{self.role}:{run_id}"

    def _episode_key(self) -> str:
        return f"aqp:mem:episode:{self.role}"

    def _reflection_key(self) -> str:
        return f"aqp:mem:reflect:{self.role}"

    # ------------------------------------------------------------------ working
    def working_push(self, run_id: str, message: str, *, role: str = "agent") -> None:
        if self._redis is None or not run_id:
            return
        try:
            payload = json.dumps({"role": role, "content": message}, default=str)
            self._redis.lpush(self._working_key(run_id), payload)
            self._redis.ltrim(self._working_key(run_id), 0, self.working_max - 1)
        except Exception:  # pragma: no cover
            logger.debug("Working memory push failed", exc_info=True)

    def working_recent(self, run_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        if self._redis is None or not run_id:
            return []
        n = max(1, int(limit or self.working_max))
        try:
            raw = self._redis.lrange(self._working_key(run_id), 0, n - 1)
        except Exception:  # pragma: no cover
            return []
        out: list[dict[str, Any]] = []
        for item in raw:
            try:
                out.append(json.loads(item))
            except Exception:
                out.append({"role": "agent", "content": item})
        return out

    def working_clear(self, run_id: str) -> None:
        if self._redis is None or not run_id:
            return
        try:
            self._redis.delete(self._working_key(run_id))
        except Exception:  # pragma: no cover
            pass

    # ------------------------------------------------------------------ episodic
    def remember_episode(
        self,
        situation: str,
        lesson: str,
        outcome: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        eid = self.bm25.add(situation, lesson, outcome, metadata or {})
        if self._redis is not None:
            try:
                payload = json.dumps(
                    {
                        "id": eid,
                        "situation": situation,
                        "lesson": lesson,
                        "outcome": outcome,
                        "metadata": metadata or {},
                    },
                    default=str,
                )
                self._redis.zadd(self._episode_key(), {payload: float(outcome or 0.0)})
            except Exception:  # pragma: no cover
                pass
        if self.rag is not None:
            try:
                from aqp.rag.indexers.decisions_indexer import index_decision_payloads

                index_decision_payloads(
                    [
                        {
                            "id": eid,
                            "vt_symbol": (metadata or {}).get("vt_symbol", ""),
                            "as_of": (metadata or {}).get("as_of", ""),
                            "text": f"Situation: {situation}\nLesson: {lesson}\nOutcome: {outcome}",
                        }
                    ],
                    rag=self.rag,
                )
            except Exception:  # pragma: no cover
                logger.debug("Skip RAG indexing of episode", exc_info=True)
        return eid

    def recall_episodes(self, query: str, k: int = 5) -> list[MemoryEntry]:
        return self.bm25.recall(query, k=k)

    # ------------------------------------------------------------------ reflections
    def reflect(
        self,
        lesson: str,
        *,
        situation: str = "reflection",
        outcome: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        eid = self.bm25.add(situation, lesson, outcome, metadata or {})
        if self._redis is not None:
            try:
                payload = json.dumps(
                    {"id": eid, "lesson": lesson, "outcome": outcome, "metadata": metadata or {}},
                    default=str,
                )
                self._redis.lpush(self._reflection_key(), payload)
                self._redis.ltrim(self._reflection_key(), 0, 256)
            except Exception:  # pragma: no cover
                pass
        return eid

    def recall_reflections(self, query: str, k: int = 5) -> list[str]:
        out = [e.lesson for e in self.bm25.recall(query, k)]
        if self.rag is not None:
            try:
                hits = self.rag.query(query, level="l0", corpus="decisions", k=k)
                out.extend(h.text for h in hits)
            except Exception:  # pragma: no cover
                pass
        seen: set[str] = set()
        deduped: list[str] = []
        for s in out:
            if s in seen:
                continue
            seen.add(s)
            deduped.append(s)
        return deduped[:k]


__all__ = [
    "BM25Memory",
    "HybridMemory",
    "MemoryEntry",
    "RedisHybridMemory",
]
