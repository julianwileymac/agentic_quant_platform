"""Data Lab foundation: lab_graphs, lab_runs, lab_node_runs, lab_artifacts,
lab_snippets, lab_labels, lab_notes, lab_paper_chunks.

Revision ID: 0057_data_lab_foundation
Revises: 0056_entra_tenant_link_nullable_org
Create Date: 2026-05-20

Strictly additive. The new tables back the four-mode Data Lab page
(EDA / Testing / Evaluation / Simulation) and live alongside the
existing ``analysis_runs`` / ``workflow_runs`` / ``rl_runs`` /
``bot_versions`` tables — nothing pre-existing is altered.

Tenancy / governance hooks:

- Every run-producing table carries ``experiment_id`` + ``test_id``
  FKs per AGENTS rule 34. :class:`aqp.persistence.ledger.LedgerWriter`
  stamps them from the active ``RequestContext`` automatically.
- ``lab_graphs`` mirrors :class:`ProjectScopedMixin` columns
  (workspace / project / owner) plus an explicit ``lab_id`` FK because
  graphs live inside a research :class:`Lab` (the existing
  ``QuantBook`` analog from ``aqp/persistence/models_tenancy.py``).
- ``lab_graphs.content_hash`` is the SHA256 of canonical-JSON
  ``GraphSpec`` (mirrors :meth:`aqp.agents.orchestration.spec.WorkflowSpec.snapshot_hash`);
  every replay-from-history button reconstructs a fresh ``GraphSpec``
  from this hash + ``data_snapshot`` + ``code_snapshot``.
- ``lab_paper_chunks.embedding`` reuses the pgvector machinery added
  in migration 0045 (BGE-M3 / 1024 dim by default). On SQLite test
  environments the pgvector branch is skipped — the chunks table
  still gets created so application code can insert / query rows
  without dimensional similarity.

Mode is enforced via a CHECK constraint to one of
``eda | testing | evaluation | simulation``.

AGENTS rule 6: this migration is **immutable** once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision = "0057_data_lab_foundation"
down_revision = "0056_entra_tenant_link_nullable_org"
branch_labels = None
depends_on = None


# Matches PGVECTOR_DIM in migration 0045 (BGE-M3).
PGVECTOR_DIM = 1024

_MODE_CHECK = "mode IN ('eda','testing','evaluation','simulation')"
_RUN_STATUS_CHECK = (
    "status IN ('pending','queued','running','done','error','cancelled','halted')"
)
_NODE_STATUS_CHECK = (
    "status IN ('pending','queued','running','done','error','cached','skipped')"
)


def _jsonb() -> sa.types.TypeEngine:
    """JSON column that promotes to JSONB on Postgres for GIN-able payloads."""
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else ""

    # ------------------------------------------------------------------
    # 1. lab_graphs — content-addressed GraphSpec documents
    # ------------------------------------------------------------------
    op.create_table(
        "lab_graphs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "lab_id",
            sa.String(length=36),
            sa.ForeignKey("labs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mode", sa.String(length=24), nullable=False, index=True),
        sa.Column(
            "spec",
            _jsonb(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False, index=True),
        sa.Column(
            "parent_graph_id",
            sa.String(length=36),
            sa.ForeignKey("lab_graphs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "data_snapshot",
            _jsonb(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("code_snapshot", sa.String(length=64), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(_MODE_CHECK, name="ck_lab_graphs_mode"),
        sa.UniqueConstraint(
            "lab_id",
            "content_hash",
            name="uq_lab_graphs_lab_content_hash",
        ),
    )
    op.create_index(
        "ix_lab_graphs_lab_mode",
        "lab_graphs",
        ["lab_id", "mode"],
    )
    op.create_index(
        "ix_lab_graphs_updated_desc",
        "lab_graphs",
        [sa.text("updated_at DESC")],
    )
    if dialect == "postgresql":
        op.create_index(
            "ix_lab_graphs_spec_gin",
            "lab_graphs",
            ["spec"],
            postgresql_using="gin",
        )

    # ------------------------------------------------------------------
    # 2. lab_runs — one row per GraphSpec submission
    # ------------------------------------------------------------------
    op.create_table(
        "lab_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "graph_id",
            sa.String(length=36),
            sa.ForeignKey("lab_graphs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "lab_id",
            sa.String(length=36),
            sa.ForeignKey("labs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "experiment_id",
            sa.String(length=36),
            sa.ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "test_id",
            sa.String(length=36),
            sa.ForeignKey("aqp_tests.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("mode", sa.String(length=24), nullable=False, index=True),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="pending",
            index=True,
        ),
        sa.Column("session_id", sa.String(length=120), nullable=True, index=True),
        sa.Column("task_id", sa.String(length=120), nullable=True, index=True),
        sa.Column("celery_root_id", sa.String(length=120), nullable=True),
        sa.Column("dagster_run_id", sa.String(length=120), nullable=True),
        sa.Column(
            "workflow_run_id",
            sa.String(length=36),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "analysis_run_id",
            sa.String(length=36),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "rl_run_id",
            sa.String(length=36),
            nullable=True,
            index=True,
        ),
        sa.Column("mlflow_run_id", sa.String(length=120), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False, index=True),
        sa.Column(
            "metrics",
            _jsonb(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "result_summary",
            _jsonb(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "data_snapshot",
            _jsonb(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("code_snapshot", sa.String(length=64), nullable=True),
        sa.Column(
            "total_trials_searched",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("halted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("halt_reason", sa.String(length=240), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.CheckConstraint(_MODE_CHECK, name="ck_lab_runs_mode"),
        sa.CheckConstraint(_RUN_STATUS_CHECK, name="ck_lab_runs_status"),
    )
    op.create_index(
        "ix_lab_runs_status_started_desc",
        "lab_runs",
        ["status", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_lab_runs_graph_started_desc",
        "lab_runs",
        ["graph_id", sa.text("started_at DESC")],
    )

    # ------------------------------------------------------------------
    # 3. lab_node_runs — per-node execution row
    # ------------------------------------------------------------------
    op.create_table(
        "lab_node_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("lab_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("node_id", sa.String(length=120), nullable=False, index=True),
        sa.Column("node_type", sa.String(length=120), nullable=False, index=True),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="pending",
            index=True,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column(
            "output_locator",
            _jsonb(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "metrics",
            _jsonb(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("log_label", sa.String(length=240), nullable=True),
        sa.CheckConstraint(_NODE_STATUS_CHECK, name="ck_lab_node_runs_status"),
        sa.UniqueConstraint(
            "run_id", "node_id", name="uq_lab_node_runs_run_node"
        ),
    )
    op.create_index(
        "ix_lab_node_runs_run_status",
        "lab_node_runs",
        ["run_id", "status"],
    )

    # ------------------------------------------------------------------
    # 4. lab_artifacts — files / Arrow tables / tearsheets produced by a node
    # ------------------------------------------------------------------
    op.create_table(
        "lab_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("lab_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("node_id", sa.String(length=120), nullable=True, index=True),
        sa.Column("kind", sa.String(length=64), nullable=False, index=True),
        sa.Column("uri", sa.String(length=960), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "schema_json",
            _jsonb(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=True, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_lab_artifacts_run_kind",
        "lab_artifacts",
        ["run_id", "kind"],
    )

    # ------------------------------------------------------------------
    # 5. lab_snippets — user-saved Python / SQL snippets
    # ------------------------------------------------------------------
    op.create_table(
        "lab_snippets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "lab_id",
            sa.String(length=36),
            sa.ForeignKey("labs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("language", sa.String(length=24), nullable=False, server_default="python"),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "manifest",
            _jsonb(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False, index=True),
        sa.Column("ast_safe", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "parent_snippet_id",
            sa.String(length=36),
            sa.ForeignKey("lab_snippets.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "promoted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            index=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "language IN ('python','sql')",
            name="ck_lab_snippets_language",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "name",
            "version",
            name="uq_lab_snippets_workspace_name_version",
        ),
    )

    # ------------------------------------------------------------------
    # 6. lab_labels — user-authored OHLCV annotations
    # ------------------------------------------------------------------
    op.create_table(
        "lab_labels",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "lab_id",
            sa.String(length=36),
            sa.ForeignKey("labs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("vt_symbol", sa.String(length=120), nullable=False, index=True),
        sa.Column("interval", sa.String(length=24), nullable=False, server_default="1m"),
        sa.Column("t_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("t_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False, index=True),
        sa.Column(
            "payload",
            _jsonb(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("lab_runs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "kind IN ('support_resistance','trendline','swing','regime_band',"
            "'pattern','order_event','annotation')",
            name="ck_lab_labels_kind",
        ),
    )
    op.create_index(
        "ix_lab_labels_lab_symbol",
        "lab_labels",
        ["lab_id", "vt_symbol"],
    )
    if dialect == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_lab_labels_t_start_brin "
            "ON lab_labels USING brin (t_start);"
        )
    else:
        op.create_index(
            "ix_lab_labels_t_start",
            "lab_labels",
            ["t_start"],
        )

    # ------------------------------------------------------------------
    # 7. lab_notes — markdown notes attached to graphs / runs / labels
    # ------------------------------------------------------------------
    op.create_table(
        "lab_notes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "lab_id",
            sa.String(length=36),
            sa.ForeignKey("labs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "author_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("target_kind", sa.String(length=24), nullable=False, index=True),
        sa.Column("target_id", sa.String(length=120), nullable=False, index=True),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column(
            "citations",
            _jsonb(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "target_kind IN ('graph','run','node_run','label','paper_chunk','snippet')",
            name="ck_lab_notes_target_kind",
        ),
    )
    op.create_index(
        "ix_lab_notes_target",
        "lab_notes",
        ["target_kind", "target_id"],
    )

    # ------------------------------------------------------------------
    # 8. lab_paper_chunks — supplementary chunk table beside RagCorpus
    # ------------------------------------------------------------------
    # We do NOT replace the existing RagChunk / RagCorpus tables; they
    # remain the canonical research-paper surface for the labs router.
    # ``lab_paper_chunks`` adds a denormalised slice with pgvector-
    # indexed embeddings keyed to the parent ``rag_chunks.id`` so the
    # Data Lab's hybrid retrieval (BM25 + dense + MMR) can index its
    # own filtered view without changing the upstream corpus.
    op.create_table(
        "lab_paper_chunks",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "lab_id",
            sa.String(length=36),
            sa.ForeignKey("labs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "rag_chunk_id",
            sa.String(length=64),
            nullable=True,
            index=True,
        ),
        sa.Column("paper_title", sa.String(length=400), nullable=True),
        sa.Column("source_uri", sa.String(length=960), nullable=True),
        sa.Column("chunk_ord", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
        sa.Column(
            "embedding",
            postgresql.ARRAY(sa.Float()),
            nullable=True,
        ),
        sa.Column(
            "metadata_json",
            _jsonb(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    if dialect == "postgresql":
        op.execute(
            f"ALTER TABLE lab_paper_chunks "
            f"ALTER COLUMN embedding TYPE vector({PGVECTOR_DIM}) "
            f"USING NULL"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS lab_paper_chunks_embedding_hnsw_idx "
            "ON lab_paper_chunks "
            "USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64);"
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else ""

    if dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS lab_paper_chunks_embedding_hnsw_idx;")
    op.drop_table("lab_paper_chunks")

    op.drop_index("ix_lab_notes_target", table_name="lab_notes")
    op.drop_table("lab_notes")

    if dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_lab_labels_t_start_brin;")
    else:
        op.drop_index("ix_lab_labels_t_start", table_name="lab_labels")
    op.drop_index("ix_lab_labels_lab_symbol", table_name="lab_labels")
    op.drop_table("lab_labels")

    op.drop_table("lab_snippets")

    op.drop_index("ix_lab_artifacts_run_kind", table_name="lab_artifacts")
    op.drop_table("lab_artifacts")

    op.drop_index("ix_lab_node_runs_run_status", table_name="lab_node_runs")
    op.drop_table("lab_node_runs")

    op.drop_index("ix_lab_runs_graph_started_desc", table_name="lab_runs")
    op.drop_index("ix_lab_runs_status_started_desc", table_name="lab_runs")
    op.drop_table("lab_runs")

    if dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_lab_graphs_spec_gin;")
    op.drop_index("ix_lab_graphs_updated_desc", table_name="lab_graphs")
    op.drop_index("ix_lab_graphs_lab_mode", table_name="lab_graphs")
    op.drop_table("lab_graphs")
