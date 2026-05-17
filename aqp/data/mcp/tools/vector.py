"""``data.vector.*`` + ``data.embeddings.compute`` DataMCP tools.

Phase 3 — exposes the pgvector control plane to agents through the
standard DataMCP boundary (AGENTS rule 22). The MCP tools call
:class:`aqp.rag.pgvector_store.PgVectorStore` rather than emitting SQL
inline so the back-end can swap (e.g. pg ↔ remote search service)
without touching agent specs.

``data.embeddings.compute`` does NOT call an LLM. Embedding generation
goes through the canonical :class:`aqp.rag.embedder.Embedder`
(SentenceTransformer / BGE-M3 by default).
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


_ALLOWED_TABLES = {
    "rag_chunks",
    "codebase_symbol_embeddings",
    "ml_feature_vectors",
}


def _validate_table(name: str) -> str:
    """Hard whitelist — agents may only target known pgvector tables.

    Mirrors the AGENTS rule 29 + 22 contract: free-text identifiers
    are forbidden when the universe is bounded.
    """
    if name not in _ALLOWED_TABLES:
        raise ValueError(
            f"table {name!r} is not in the pgvector allow-list {sorted(_ALLOWED_TABLES)}"
        )
    return name


def _embed_text(text: str) -> list[float]:
    try:
        from aqp.rag.embedder import Embedder
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"aqp.rag.embedder not importable: {exc}") from exc
    embedder = Embedder.get_default() if hasattr(Embedder, "get_default") else Embedder()
    vec = embedder.embed_one(str(text)) if hasattr(embedder, "embed_one") else embedder.embed([str(text)])[0]
    return [float(x) for x in vec]


# ---------------------------------------------------------------------------
# data.vector.search
# ---------------------------------------------------------------------------


class VectorSearchInput(BaseModel):
    table: str = Field(..., description="One of rag_chunks / codebase_symbol_embeddings / ml_feature_vectors.")
    query: str | None = Field(
        default=None,
        description="Free-text query — embedded via the canonical embedder before search.",
    )
    embedding: list[float] | None = Field(
        default=None,
        description="Pre-computed query vector. Mutually exclusive with `query`.",
    )
    k: int = Field(default=10, ge=1, le=200)
    distance: str = Field(default="cosine", pattern=r"^(cosine|l2|inner)$")
    where: str | None = Field(
        default=None,
        description="Optional SQL WHERE fragment (no semicolons; AND clauses only).",
    )


@register_data_mcp_tool
class VectorSearchTool(DataMCPTool):
    name = "data.vector.search"
    description = (
        "Similarity search over a pgvector-backed table. Pass either "
        "`query` (free-text — embedded by the canonical embedder) or "
        "`embedding` (pre-computed vector). Returns the top-k rows "
        "ordered by ascending distance."
    )
    args_schema = VectorSearchInput
    category = "vector"
    tags = ("pgvector", "search")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        table: str,
        query: str | None = None,
        embedding: list[float] | None = None,
        k: int = 10,
        distance: str = "cosine",
        where: str | None = None,
    ) -> MCPToolResult:
        try:
            table = _validate_table(table)
        except ValueError as exc:
            return MCPToolResult(ok=False, error=str(exc), summary="bad table")
        if where and ";" in where:
            return MCPToolResult(
                ok=False, error="WHERE must not contain semicolons", summary="bad where"
            )
        if not embedding:
            if not query:
                return MCPToolResult(
                    ok=False, error="must pass `query` or `embedding`", summary="no query"
                )
            try:
                embedding = _embed_text(query)
            except Exception as exc:  # noqa: BLE001
                return MCPToolResult(
                    ok=False, error=f"embedding failed: {exc}", summary="embed failed"
                )

        try:
            from aqp.rag.pgvector_store import PgVectorStore
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False, error=f"pgvector_store unavailable: {exc}", summary="store unavailable"
            )

        store = PgVectorStore(table=table)
        try:
            hits = store.query(
                embedding=embedding,
                k=int(k),
                distance=distance,
                where=where,
            )
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False, error=f"pgvector query failed: {exc}", summary="search failed"
            )
        return MCPToolResult(
            ok=True,
            data={
                "table": table,
                "k": int(k),
                "distance": distance,
                "hits": [
                    {"text": h.text, "score": h.score, "metadata": h.metadata}
                    for h in hits
                ],
            },
            rows_returned=len(hits),
            summary=f"{len(hits)} pgvector hits",
        )


# ---------------------------------------------------------------------------
# data.vector.upsert
# ---------------------------------------------------------------------------


class VectorUpsertInput(BaseModel):
    table: str
    rows: list[dict[str, Any]] = Field(..., min_length=1, max_length=500)


@register_data_mcp_tool
class VectorUpsertTool(DataMCPTool):
    name = "data.vector.upsert"
    description = (
        "Insert rows into a pgvector-backed table. Used by ingestion "
        "pipelines that produce embeddings outside HierarchicalRAG "
        "(e.g. ML feature snapshots). For RAG corpus writes, prefer "
        "HierarchicalRAG.index_chunks via aqp.rag.indexers."
    )
    args_schema = VectorUpsertInput
    category = "vector"
    tags = ("pgvector", "write")
    required_scopes = ("data:write",)
    mutates = True

    def run(
        self,
        *,
        ctx: MCPToolContext,
        table: str,
        rows: list[dict[str, Any]],
    ) -> MCPToolResult:
        try:
            table = _validate_table(table)
        except ValueError as exc:
            return MCPToolResult(ok=False, error=str(exc), summary="bad table")
        try:
            from aqp.rag.pgvector_store import PgVectorStore
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False, error=f"pgvector_store unavailable: {exc}", summary="store unavailable"
            )
        store = PgVectorStore(table=table)
        try:
            count = store.upsert(rows=rows)
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False, error=f"pgvector upsert failed: {exc}", summary="upsert failed"
            )
        return MCPToolResult(
            ok=True,
            data={"table": table, "rows_inserted": count},
            rows_returned=count,
            summary=f"upserted {count} rows into {table}",
        )


# ---------------------------------------------------------------------------
# data.vector.delete
# ---------------------------------------------------------------------------


class VectorDeleteInput(BaseModel):
    table: str
    where: str = Field(..., min_length=1, description="Mandatory WHERE clause — no full table wipes.")


@register_data_mcp_tool
class VectorDeleteTool(DataMCPTool):
    name = "data.vector.delete"
    description = (
        "Delete rows from a pgvector-backed table. The WHERE clause is "
        "mandatory; full-table wipes are not supported through this tool."
    )
    args_schema = VectorDeleteInput
    category = "vector"
    tags = ("pgvector", "delete")
    required_scopes = ("data:write",)
    mutates = True

    def run(
        self,
        *,
        ctx: MCPToolContext,
        table: str,
        where: str,
    ) -> MCPToolResult:
        try:
            table = _validate_table(table)
        except ValueError as exc:
            return MCPToolResult(ok=False, error=str(exc), summary="bad table")
        if ";" in where:
            return MCPToolResult(
                ok=False, error="WHERE must not contain semicolons", summary="bad where"
            )
        try:
            from aqp.rag.pgvector_store import PgVectorStore
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False, error=f"pgvector_store unavailable: {exc}", summary="store unavailable"
            )
        store = PgVectorStore(table=table)
        try:
            count = store.delete(where=where)
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False, error=f"pgvector delete failed: {exc}", summary="delete failed"
            )
        return MCPToolResult(
            ok=True,
            data={"table": table, "rows_deleted": count},
            rows_returned=count,
            summary=f"deleted {count} rows from {table}",
        )


# ---------------------------------------------------------------------------
# data.embeddings.compute (no LLM — canonical embedder only)
# ---------------------------------------------------------------------------


class ComputeEmbeddingInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)


@register_data_mcp_tool
class ComputeEmbeddingTool(DataMCPTool):
    name = "data.embeddings.compute"
    description = (
        "Embed a single text string with the canonical AQP embedder "
        "(SentenceTransformer / BGE-M3 by default). Returns the raw "
        "vector — no LLM is involved. Used by agents that want to "
        "search pgvector with a pre-computed embedding."
    )
    args_schema = ComputeEmbeddingInput
    category = "embeddings"
    tags = ("embeddings", "compute")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        text: str,
    ) -> MCPToolResult:
        try:
            vec = _embed_text(text)
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False, error=f"embedding failed: {exc}", summary="embed failed"
            )
        return MCPToolResult(
            ok=True,
            data={"dim": len(vec), "embedding": vec},
            summary=f"embedded text ({len(vec)} dims)",
        )


__all__: list[str] = []
