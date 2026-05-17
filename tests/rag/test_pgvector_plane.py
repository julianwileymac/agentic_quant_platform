"""Tests for the Phase 3 pgvector control plane.

Covers:

- ``data.vector.*`` MCP tools and ``data.embeddings.compute`` are
  registered.
- :class:`PgVectorDataset` validates its spec (rejects empty table,
  rejects unknown distance).
- :func:`Vector` type helper degrades gracefully to ARRAY / JSON when
  pgvector is missing — the ORM imports must stay clean.
- :class:`PgVectorStore` constructs distance literals correctly
  without touching the database (covered by a mock-engine roundtrip).
- The ``vector_indexes`` cache category is registered.
- The ``code_chunks`` corpus is wired in the order catalog.
"""
from __future__ import annotations

import pytest


def test_data_vector_tools_registered():
    from aqp.data.mcp.registry import DATA_MCP_TOOLS

    expected = {
        "data.vector.search",
        "data.vector.upsert",
        "data.vector.delete",
        "data.embeddings.compute",
    }
    assert expected <= set(DATA_MCP_TOOLS)


def test_pgvector_dataset_spec_validation():
    from aqp.data.datasets.kinds.pgvector import PgVectorDataset
    from aqp.data.datasets.spec import DatasetSpec

    # Missing table -> ValueError.
    with pytest.raises(ValueError, match="table"):
        PgVectorDataset(DatasetSpec(kind="pgvector", config={}))
    # Unknown distance -> ValueError.
    with pytest.raises(ValueError, match="distance"):
        PgVectorDataset(
            DatasetSpec(
                kind="pgvector",
                config={"table": "rag_chunks", "distance": "hamming"},
            )
        )
    # Happy path constructs cleanly.
    ds = PgVectorDataset(
        DatasetSpec(
            kind="pgvector",
            config={"table": "rag_chunks", "distance": "cosine"},
        )
    )
    assert ds.spec.config["table"] == "rag_chunks"
    assert ds.kind == "pgvector"


def test_vector_type_helper_resolves():
    from aqp.persistence.types import Vector

    col_type = Vector(8)
    # Whichever branch wins (pgvector / ARRAY / JSON), the result must
    # be a SQLAlchemy TypeEngine instance.
    import sqlalchemy as sa

    assert isinstance(col_type, sa.types.TypeEngine)


def test_vector_indexes_cache_category_registered():
    from aqp.cache.keys import CACHE_CATEGORIES

    assert "vector_indexes" in CACHE_CATEGORIES


def test_code_chunks_corpus_registered():
    from aqp.rag.orders import OrderCatalog

    by_name = {c.name: c for c in OrderCatalog}
    assert "code_chunks" in by_name
    assert by_name["code_chunks"].order == "theory"
    assert by_name["code_chunks"].l1 == "codebase"


def test_pgvector_store_constructs_vector_literal():
    from aqp.rag.pgvector_store import PgVectorStore

    store = PgVectorStore(table="rag_chunks")
    literal = store._vec_literal([1.0, 2.5, -3.125])
    assert literal == "[1.000000,2.500000,-3.125000]"


def test_data_vector_search_rejects_unknown_table():
    from aqp.data.mcp.base import MCPToolContext
    from aqp.data.mcp.registry import get_data_mcp_tool

    tool = get_data_mcp_tool("data.vector.search")
    res = tool.invoke(
        ctx=MCPToolContext(granted_scopes=("data:read",)),
        table="not_a_real_table",
        embedding=[0.0] * 4,
        k=1,
    )
    assert res.ok is False
    assert "allow-list" in (res.error or "")


def test_data_vector_search_requires_query_or_embedding():
    from aqp.data.mcp.base import MCPToolContext
    from aqp.data.mcp.registry import get_data_mcp_tool

    tool = get_data_mcp_tool("data.vector.search")
    res = tool.invoke(
        ctx=MCPToolContext(granted_scopes=("data:read",)),
        table="rag_chunks",
    )
    assert res.ok is False
    assert "query" in (res.error or "")


def test_data_vector_search_rejects_semicolon_in_where():
    from aqp.data.mcp.base import MCPToolContext
    from aqp.data.mcp.registry import get_data_mcp_tool

    tool = get_data_mcp_tool("data.vector.search")
    res = tool.invoke(
        ctx=MCPToolContext(granted_scopes=("data:read",)),
        table="rag_chunks",
        embedding=[0.0] * 4,
        where="1=1; DROP TABLE rag_chunks",
    )
    assert res.ok is False
    assert "semicolons" in (res.error or "")


def test_data_vector_upsert_requires_write_scope():
    from aqp.data.mcp.base import MCPToolContext
    from aqp.data.mcp.registry import get_data_mcp_tool

    tool = get_data_mcp_tool("data.vector.upsert")
    res = tool.invoke(
        ctx=MCPToolContext(granted_scopes=("data:read",)),
        table="rag_chunks",
        rows=[{"id": "x"}],
    )
    assert res.ok is False
    assert "policy" in (res.error or "").lower()


def test_data_vector_delete_requires_where_clause():
    from aqp.data.mcp.base import MCPToolContext
    from aqp.data.mcp.registry import get_data_mcp_tool

    tool = get_data_mcp_tool("data.vector.delete")
    res = tool.invoke(
        ctx=MCPToolContext(granted_scopes=("data:read", "data:write")),
        table="rag_chunks",
        where="",
    )
    # Validator rejects empty where.
    assert res.ok is False


def test_pgvector_dataset_registered_in_kinds_registry():
    from aqp.data.datasets.registry import list_dataset_kinds

    kinds = list_dataset_kinds()
    assert "pgvector" in kinds
