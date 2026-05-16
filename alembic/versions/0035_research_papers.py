"""Research paper corpus storage.

Revision ID: 0035_research_papers
Revises: 0034_dagster_sandbox_sessions
Create Date: 2026-05-16

Adds the ``research_papers`` table backing the math-aware RAG
ingestion pipeline (see
:mod:`aqp.rag.indexers.research_papers_indexer`). Each row tracks a
single PDF + its rich metadata so the document library and the
``data.research_papers.*`` DataMCPTool can browse and filter without
re-parsing the PDF.

AGENTS.md rule 6: this migration is **immutable** once shipped — any
future schema change goes into a new revision.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0035_research_papers"
down_revision = "0034_dagster_sandbox_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_papers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("authors", sa.JSON(), nullable=True),  # list[str]
        sa.Column("author_institution", sa.String(length=256), nullable=True),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("asset_class", sa.JSON(), nullable=True),  # list[str]
        sa.Column("strategy_family", sa.String(length=64), nullable=True),
        sa.Column("contains_mathematics", sa.Boolean(), nullable=True),
        sa.Column("equation_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("pdf_path", sa.String(length=1024), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("parser_used", sa.String(length=32), nullable=True),
        sa.Column("vt_symbol", sa.String(length=64), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        # ProjectScopedMixin
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_papers_strategy_family",
        "research_papers",
        ["strategy_family"],
    )
    op.create_index(
        "ix_research_papers_author_institution",
        "research_papers",
        ["author_institution"],
    )
    op.create_index(
        "ix_research_papers_publication_year",
        "research_papers",
        ["publication_year"],
    )
    op.create_index(
        "ix_research_papers_workspace_strategy",
        "research_papers",
        ["workspace_id", "strategy_family"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_papers_workspace_strategy",
        table_name="research_papers",
    )
    op.drop_index(
        "ix_research_papers_publication_year",
        table_name="research_papers",
    )
    op.drop_index(
        "ix_research_papers_author_institution",
        table_name="research_papers",
    )
    op.drop_index(
        "ix_research_papers_strategy_family",
        table_name="research_papers",
    )
    op.drop_table("research_papers")
