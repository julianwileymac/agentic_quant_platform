"""Phase 3 — pgvector foundation.

Revision ID: 0045_pgvector_foundation
Revises: 0044_pricing_context_runs
Create Date: 2026-05-17

Sits the pgvector control plane beside the existing Redis + RediSearch
hierarchical RAG. Postgres is now the source-of-truth for embeddings
that need ACID joins with relational rows (`rag_chunks.embedding`,
codebase symbols, audit-graded ML feature vectors). The default
embedding dimension is 1024 (BGE-M3, matching
``aqp.rag.embedder``); we record the producing model on every row so
dimension drift is detectable.

The migration is **idempotent** w.r.t. the ``CREATE EXTENSION`` call:
``IF NOT EXISTS`` lets the upgrade run on a fresh database (where the
extension is missing) and on an existing one (where another tenant
already created it).

When the host Postgres image is plain ``postgres:16-alpine``, the
``CREATE EXTENSION`` call FAILS — the operator must move to
``pgvector/pgvector:pg16`` first. The migration leaves a clear error
message in that case rather than silently no-op'ing.

AGENTS rule 6: this migration is **immutable** once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0045_pgvector_foundation"
down_revision = "0044_pricing_context_runs"
branch_labels = None
depends_on = None


# Default dimension = BGE-M3 (1024). Other embedding models record
# their own dim via the ``embedding_model`` discriminator column.
PGVECTOR_DIM = 1024


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else ""

    if dialect != "postgresql":
        # The dataset kind + RAG backend are still importable in
        # SQLite test environments; the migration just becomes a
        # no-op so the upgrade chain stays linear.
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # ------------------------------------------------------------------
    # rag_chunks — additive columns + HNSW cosine index
    # ------------------------------------------------------------------
    op.add_column(
        "rag_chunks",
        sa.Column("embedding", sa.dialects.postgresql.ARRAY(sa.Float()), nullable=True),
    )
    # Replace the ARRAY shim with the real ``vector(N)`` type. SQLAlchemy
    # does not ship a vector dialect by default, so we patch the
    # column via raw DDL — the type is what pgvector exposes.
    op.execute(
        f'ALTER TABLE rag_chunks '
        f'ALTER COLUMN embedding TYPE vector({PGVECTOR_DIM}) '
        f'USING NULL'
    )
    op.add_column(
        "rag_chunks",
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "rag_chunks",
        sa.Column("embedding_norm", sa.Float(), nullable=True),
    )
    op.add_column(
        "rag_chunks",
        sa.Column("embedding_at", sa.DateTime(), nullable=True),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS rag_chunks_embedding_hnsw_idx "
        "ON rag_chunks "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64);"
    )

    # ------------------------------------------------------------------
    # codebase_symbol_embeddings — Phase 2's ``code_chunks`` corpus
    # ------------------------------------------------------------------
    op.create_table(
        "codebase_symbol_embeddings",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("repo", sa.String(length=240), nullable=False),
        sa.Column("file_path", sa.String(length=960), nullable=False),
        sa.Column("symbol_name", sa.String(length=240), nullable=False),
        sa.Column("symbol_kind", sa.String(length=40), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=24), nullable=True),
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
        # Raw vector column patched in below.
        sa.Column("embedding", sa.dialects.postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column("hash", sa.String(length=128), nullable=False),
        sa.Column("indexed_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.UniqueConstraint("hash", name="uq_codebase_symbol_embeddings_hash"),
    )
    op.execute(
        f'ALTER TABLE codebase_symbol_embeddings '
        f'ALTER COLUMN embedding TYPE vector({PGVECTOR_DIM}) '
        f'USING NULL'
    )
    op.create_index(
        "ix_codebase_symbol_embeddings_repo_file",
        "codebase_symbol_embeddings",
        ["repo", "file_path"],
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS codebase_symbol_embeddings_embedding_hnsw_idx "
        "ON codebase_symbol_embeddings "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64);"
    )

    # ------------------------------------------------------------------
    # ml_feature_vectors — audit-graded ML feature snapshots
    # ------------------------------------------------------------------
    op.create_table(
        "ml_feature_vectors",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("experiment_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("symbol", sa.String(length=120), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=True),
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
        sa.Column("embedding", sa.dialects.postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
    )
    op.execute(
        f'ALTER TABLE ml_feature_vectors '
        f'ALTER COLUMN embedding TYPE vector({PGVECTOR_DIM}) '
        f'USING NULL'
    )
    op.create_index(
        "ix_ml_feature_vectors_experiment",
        "ml_feature_vectors",
        ["experiment_id"],
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ml_feature_vectors_embedding_hnsw_idx "
        "ON ml_feature_vectors "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64);"
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else ""
    if dialect != "postgresql":
        return

    op.execute("DROP INDEX IF EXISTS ml_feature_vectors_embedding_hnsw_idx;")
    op.drop_index("ix_ml_feature_vectors_experiment", table_name="ml_feature_vectors")
    op.drop_table("ml_feature_vectors")

    op.execute("DROP INDEX IF EXISTS codebase_symbol_embeddings_embedding_hnsw_idx;")
    op.drop_index(
        "ix_codebase_symbol_embeddings_repo_file",
        table_name="codebase_symbol_embeddings",
    )
    op.drop_table("codebase_symbol_embeddings")

    op.execute("DROP INDEX IF EXISTS rag_chunks_embedding_hnsw_idx;")
    op.drop_column("rag_chunks", "embedding_at")
    op.drop_column("rag_chunks", "embedding_norm")
    op.drop_column("rag_chunks", "embedding_model")
    op.drop_column("rag_chunks", "embedding")
    # ``DROP EXTENSION vector`` is deliberately omitted — another
    # tenant or future migration may rely on it.
