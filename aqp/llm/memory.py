"""Hybrid agent memory — BM25 for outcome-based recall, Chroma for metadata.

Inspired by TradingAgents' ``FinancialSituationMemory``: lexical BM25 avoids
per-reflection embedding cost for the high-volume trade-outcome feedback
loop, while ChromaDB handles the slower-changing research corpus.
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
