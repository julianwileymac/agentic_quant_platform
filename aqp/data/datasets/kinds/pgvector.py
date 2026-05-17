"""``pgvector`` :class:`BaseDataset` kind.

Reads / writes to pgvector-backed Postgres tables created by migration
``0045_pgvector_foundation``. The dataset is the **only sanctioned
write path** for an arbitrary embedding row outside the
:class:`HierarchicalRAG.index_chunks` flow (AGENTS rule 29).

Spec config schema::

    {
        "table": "rag_chunks",            # or codebase_symbol_embeddings / ml_feature_vectors
        "vector_column": "embedding",     # column carrying the vector(N)
        "metadata_columns": ["...","..."],
        "query": "...",                   # optional SQL for read; otherwise SELECT *
        "embedding_dim": 1024,            # default settings.pgvector_dim
        "distance": "cosine",             # cosine | l2 | inner
        "where": "...",                   # optional WHERE clause for read
        "limit": 50,
    }
"""
from __future__ import annotations

from typing import Any

from aqp.data.datasets.base import BaseDataset
from aqp.data.datasets.exceptions import DatasetSaveDisabled


_ALLOWED_DISTANCES = {"cosine", "l2", "inner"}


class PgVectorDataset(BaseDataset):
    kind = "pgvector"
    writable = True

    def _validate_spec(self) -> None:
        cfg = self._spec.config
        if not str(cfg.get("table") or "").strip():
            raise ValueError("PgVectorDataset requires config.table")
        distance = str(cfg.get("distance") or "cosine").strip().lower()
        if distance not in _ALLOWED_DISTANCES:
            raise ValueError(
                f"PgVectorDataset.distance={distance!r} must be one of "
                f"{sorted(_ALLOWED_DISTANCES)}"
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _engine(self) -> Any:
        from aqp.persistence.db import _sync_engine

        return _sync_engine()

    def _table(self) -> str:
        return str(self._spec.config["table"])

    def _vector_column(self) -> str:
        return str(self._spec.config.get("vector_column") or "embedding")

    def _distance_operator(self) -> str:
        return {
            "cosine": "<=>",
            "l2": "<->",
            "inner": "<#>",
        }[str(self._spec.config.get("distance") or "cosine").lower()]

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def _load(self) -> Any:
        import pandas as pd
        from sqlalchemy import text

        cfg = self._spec.config
        engine = self._engine()
        with engine.connect() as conn:
            if cfg.get("query"):
                return pd.read_sql_query(text(str(cfg["query"])), conn)
            where = str(cfg.get("where") or "").strip()
            limit = int(cfg.get("limit") or 100)
            sql = f"SELECT * FROM {self._table()}"
            if where:
                sql += f" WHERE {where}"
            sql += f" LIMIT {limit}"
            return pd.read_sql_query(text(sql), conn)

    # ------------------------------------------------------------------
    # Save — batched upserts
    # ------------------------------------------------------------------

    def _save(self, payload: Any) -> Any:
        if payload is None:
            return {"rows": 0}
        from sqlalchemy import text

        # Accept either a list[dict] or a DataFrame.
        try:
            import pandas as pd

            if isinstance(payload, pd.DataFrame):
                records = payload.to_dict(orient="records")
            elif isinstance(payload, list):
                records = list(payload)
            else:
                raise DatasetSaveDisabled(
                    f"PgVectorDataset._save expects DataFrame or list[dict], got {type(payload)!r}"
                )
        except ImportError:
            if not isinstance(payload, list):
                raise DatasetSaveDisabled(
                    f"PgVectorDataset._save expects list[dict] when pandas missing"
                ) from None
            records = list(payload)

        if not records:
            return {"rows": 0}
        engine = self._engine()
        table = self._table()
        columns = list(records[0].keys())
        placeholders = ", ".join(f":{c}" for c in columns)
        col_list = ", ".join(columns)
        sql = text(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})")
        with engine.begin() as conn:
            for chunk_start in range(0, len(records), 200):
                chunk = records[chunk_start: chunk_start + 200]
                conn.execute(sql, chunk)
        return {"rows": len(records), "table": table}

    # ------------------------------------------------------------------
    # Public helper used by data.vector.* MCP tools
    # ------------------------------------------------------------------

    def similarity_search(
        self,
        *,
        query_vector: list[float],
        k: int = 10,
        where: str | None = None,
    ) -> list[dict[str, Any]]:
        """Run a vector similarity search against the configured table.

        Returns ``[{...row..., "distance": float}]`` ordered by
        ascending distance.
        """
        from sqlalchemy import text

        engine = self._engine()
        op = self._distance_operator()
        vector_column = self._vector_column()
        table = self._table()
        vec_literal = "[" + ",".join(f"{float(x):.6f}" for x in query_vector) + "]"
        sql = (
            f"SELECT *, ({vector_column} {op} '{vec_literal}'::vector) AS distance "
            f"FROM {table}"
        )
        if where:
            sql += f" WHERE {where}"
        sql += f" ORDER BY distance ASC LIMIT {int(k)}"
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            rows = [dict(r._mapping) for r in result.fetchall()]
        return rows


__all__ = ["PgVectorDataset"]
