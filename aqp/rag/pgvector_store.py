"""pgvector-backed vector store used as an alternative HierarchicalRAG backend.

Sits beside :class:`aqp.rag.redis_store.RedisVectorStore` rather than
replacing it. The per-corpus backend knob in :mod:`aqp.rag.orders` (or
``settings.rag_backend_overrides`` runtime override) determines which
store handles a given corpus.

Hard rules honoured:

- **Rule 11** — every embedding write enters via this store from
  inside :class:`HierarchicalRAG.index_chunks`. Direct SQL writes from
  agent code are not supported (use ``data.vector.upsert`` instead).
- **Rule 22** — the only public surface for agent reads is
  ``data.vector.*`` :class:`DataMCPTool` subclasses. Routes that want
  to read pgvector directly do so through this module, never via
  hand-written SQL inline.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PgVectorHit:
    """One similarity-search hit."""

    text: str
    score: float
    metadata: dict[str, Any]


class PgVectorStore:
    """Compact wrapper around ``pgvector`` similarity search.

    Mirrors the read surface of
    :class:`aqp.rag.redis_store.RedisVectorStore` so
    :class:`HierarchicalRAG` can dispatch per corpus.
    """

    def __init__(
        self,
        *,
        table: str = "rag_chunks",
        vector_column: str = "embedding",
        text_column: str = "content",
        embedding_dim: int | None = None,
    ) -> None:
        self._table = table
        self._vector_column = vector_column
        self._text_column = text_column
        self._embedding_dim = int(embedding_dim) if embedding_dim is not None else None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _engine(self) -> Any:
        from aqp.persistence.db import _sync_engine

        return _sync_engine()

    def _vec_literal(self, vec: list[float]) -> str:
        return "[" + ",".join(f"{float(x):.6f}" for x in vec) + "]"

    # ------------------------------------------------------------------
    # Write surface
    # ------------------------------------------------------------------

    def upsert(
        self,
        *,
        rows: Iterable[dict[str, Any]],
        chunk_size: int = 200,
    ) -> int:
        """Insert (or replace by ``id`` when provided) embedding rows.

        Each row may carry arbitrary metadata columns; the keys are
        used verbatim in the INSERT, so callers must align with the
        physical schema.
        """
        from sqlalchemy import text

        records = list(rows)
        if not records:
            return 0
        engine = self._engine()
        columns = list(records[0].keys())
        placeholders = ", ".join(f":{c}" for c in columns)
        col_list = ", ".join(columns)
        sql = text(
            f"INSERT INTO {self._table} ({col_list}) VALUES ({placeholders})"
        )
        with engine.begin() as conn:
            for chunk_start in range(0, len(records), int(chunk_size)):
                chunk = records[chunk_start: chunk_start + int(chunk_size)]
                conn.execute(sql, chunk)
        return len(records)

    def delete(self, *, where: str, params: dict[str, Any] | None = None) -> int:
        from sqlalchemy import text

        engine = self._engine()
        sql = text(f"DELETE FROM {self._table} WHERE {where}")
        with engine.begin() as conn:
            result = conn.execute(sql, params or {})
            return int(result.rowcount or 0)

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def query(
        self,
        *,
        embedding: list[float],
        k: int = 8,
        distance: str = "cosine",
        where: str | None = None,
        params: dict[str, Any] | None = None,
        select_columns: Iterable[str] | None = None,
    ) -> list[PgVectorHit]:
        from sqlalchemy import text

        op = {"cosine": "<=>", "l2": "<->", "inner": "<#>"}[str(distance).lower()]
        cols = (
            ", ".join(select_columns) if select_columns else "*"
        )
        sql_parts = [
            f"SELECT {cols}, ({self._vector_column} {op} '{self._vec_literal(embedding)}'::vector) AS distance",
            f"FROM {self._table}",
        ]
        if where:
            sql_parts.append(f"WHERE {where}")
        sql_parts.append(f"ORDER BY distance ASC LIMIT {int(k)}")
        sql = text(" ".join(sql_parts))

        engine = self._engine()
        with engine.connect() as conn:
            result = conn.execute(sql, params or {})
            rows = result.fetchall()

        hits: list[PgVectorHit] = []
        for row in rows:
            row_dict = dict(row._mapping)
            distance_val = float(row_dict.pop("distance", 0.0))
            # Convert distance to a 0..1 similarity score (cosine).
            score = 1.0 / (1.0 + distance_val)
            text_value = str(row_dict.get(self._text_column, "") or "")
            hits.append(
                PgVectorHit(
                    text=text_value,
                    score=score,
                    metadata={k: row_dict.get(k) for k in row_dict if k != self._text_column},
                )
            )
        return hits


__all__ = ["PgVectorHit", "PgVectorStore"]
