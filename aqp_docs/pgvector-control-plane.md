# pgvector control plane (Phase 3)

The pgvector control plane adds a **second** vector store next to the
existing Redis + RediSearch HierarchicalRAG. It is additive — no
existing corpus is migrated implicitly — and it sits behind the same
`HierarchicalRAG` facade so callers never need to know which backend
holds their corpus.

## Why a second store

Redis + RediSearch HNSW remains the hot-path vector store for the
agentic RAG hierarchy. pgvector wins where vectors need to live next
to relational rows that need ACID joins:

- `rag_chunks.embedding` — same row that already carries audit /
  tenancy / lineage columns.
- `codebase_symbol_embeddings` — the Phase 2 `code_chunks` corpus
  needs `(repo, file_path, symbol_name)` joins that Redis hashes
  cannot serve cleanly.
- `ml_feature_vectors` — audit-graded ML feature snapshots that need
  `experiment_id` FK enforcement (hard rule 34).

## Hard rules

1. **Rule 3 (Iceberg writes).** pgvector is **not** an Iceberg write
   path. If a future flow needs Iceberg, route through
   `iceberg_catalog.append_arrow`.
2. **Rule 6 (Migrations).** [alembic/versions/0045_pgvector_foundation.py](../alembic/versions/0045_pgvector_foundation.py)
   is shipped — never edit it. Add `0046_*` etc.
3. **Rule 11 (RAG boundary).** `HierarchicalRAG` is the only public
   surface. `aqp/rag/pgvector_store.py` is a backend behind it.
4. **Rule 22 (DataMCP boundary).** Agents reach pgvector through
   `data.vector.*` MCP tools, never through hand-written SQL.
5. **Rule 29 (EntityPicker).** Frontend dropdowns naming a vector
   index MUST use `<EntityPicker kind="vector_indexes" />`.

## Infrastructure

- `aqp_platform/compose/docker-compose.yml` postgres image: `pgvector/pgvector:pg16` (a
  drop-in superset of `postgres:16-alpine`).
- Alembic migration `0045_pgvector_foundation` issues
  `CREATE EXTENSION IF NOT EXISTS vector`, adds the `embedding`
  column to `rag_chunks`, and creates `codebase_symbol_embeddings`
  and `ml_feature_vectors` tables.
- HNSW indexes use `m=16, ef_construction=64` (override via the
  `pgvector_hnsw_*` settings).

## Tool surface

| Tool | Mutating? | Notes |
|------|-----------|-------|
| `data.vector.search` | no | hybrid: `query` (free-text → embedded) or `embedding` (pre-computed) |
| `data.vector.upsert` | yes | requires `data:write` scope |
| `data.vector.delete` | yes | mandatory `WHERE` clause; no full-table wipes |
| `data.embeddings.compute` | no | canonical embedder, no LLM |

Only three tables are in the allow-list today:
`rag_chunks`, `codebase_symbol_embeddings`, `ml_feature_vectors`.
Add to `_ALLOWED_TABLES` in
[aqp/data/mcp/tools/vector.py](../aqp/data/mcp/tools/vector.py) to
extend.

## Frontend integration

Add a vector-index dropdown wherever the operator names a target
table: `<EntityPicker kind="vector_indexes" />`. The category is
registered in
[aqp/cache/keys.py](../aqp/cache/keys.py) and populated by the
existing `MetadataPrefetcher` pattern.

## Migration story

The default `settings.rag_backend_default = "redis"` keeps every
existing corpus on the Redis backend. The new `code_chunks` corpus is
the only one pgvector-only today
(`settings.rag_backend_overrides = "code_chunks=pgvector"`).

To move a corpus, flip its entry in
`settings.rag_backend_overrides` to `dual` (writes both backends,
reads from Redis), backfill via the existing indexer, validate
parity, then flip to `pgvector`.
