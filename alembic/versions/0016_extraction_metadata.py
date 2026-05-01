"""Extraction metadata: source/category columns + dataset_presets + extraction_audit

Revision ID: 0016_extraction_metadata
Revises: 0015_dbt_foundation
Create Date: 2026-04-29

Adds:
- ``source_repo``, ``source_path``, ``category``, ``extracted_at`` columns
  to ``strategies``, ``model_versions``, ``agent_specs`` so the registry
  UI can faceted-filter rehydrated content by inspiration source.
- ``dataset_presets`` table mirroring :data:`aqp.data.dataset_presets.PRESETS`.
- ``extraction_audit`` table tracking when each asset was extracted from
  which source.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_extraction_metadata"
down_revision = "0015_dbt_foundation"
branch_labels = None
depends_on = None


_EXTRACTION_COLUMNS = (
    sa.Column("source_repo", sa.String(length=200), nullable=True),
    sa.Column("source_path", sa.String(length=1024), nullable=True),
    sa.Column("category", sa.String(length=120), nullable=True),
    sa.Column("extracted_at", sa.DateTime(), nullable=True),
)


def _add_extraction_columns(table: str) -> None:
    for col in _EXTRACTION_COLUMNS:
        try:
            op.add_column(table, col.copy())
        except Exception:  # pragma: no cover - column may already exist on re-run
            pass
    try:
        op.create_index(f"ix_{table}_source_repo", table, ["source_repo"])
    except Exception:
        pass
    try:
        op.create_index(f"ix_{table}_category", table, ["category"])
    except Exception:
        pass


def _drop_extraction_columns(table: str) -> None:
    for name in ("source_repo", "source_path", "category", "extracted_at"):
        try:
            op.drop_column(table, name)
        except Exception:
            pass
    for idx in (f"ix_{table}_source_repo", f"ix_{table}_category"):
        try:
            op.drop_index(idx, table_name=table)
        except Exception:
            pass


def upgrade() -> None:
    for table in ("strategies", "model_versions", "agent_specs"):
        _add_extraction_columns(table)

    op.create_table(
        "dataset_presets",
        sa.Column("name", sa.String(length=120), primary_key=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("namespace", sa.String(length=120), nullable=False),
        sa.Column("table_name", sa.String(length=160), nullable=False),
        sa.Column("source_kind", sa.String(length=80), nullable=False),
        sa.Column("ingestion_task", sa.String(length=240), nullable=False),
        sa.Column("requires_api_key", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("api_key_env_var", sa.String(length=120), nullable=True),
        sa.Column("default_symbols", sa.JSON(), nullable=True),
        sa.Column("interval", sa.String(length=24), nullable=False, server_default="1d"),
        sa.Column("schedule_cron", sa.String(length=80), nullable=True),
        sa.Column("documentation_url", sa.String(length=1024), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_dataset_presets_namespace", "dataset_presets", ["namespace"])
    op.create_index("ix_dataset_presets_source_kind", "dataset_presets", ["source_kind"])

    op.create_table(
        "extraction_audit",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("asset_alias", sa.String(length=200), nullable=False),
        sa.Column("asset_kind", sa.String(length=60), nullable=False),
        sa.Column("source_repo", sa.String(length=200), nullable=False),
        sa.Column("source_path", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_extraction_audit_alias", "extraction_audit", ["asset_alias"])
    op.create_index("ix_extraction_audit_source_repo", "extraction_audit", ["source_repo"])
    op.create_index("ix_extraction_audit_kind", "extraction_audit", ["asset_kind"])


def downgrade() -> None:
    op.drop_index("ix_extraction_audit_kind", table_name="extraction_audit")
    op.drop_index("ix_extraction_audit_source_repo", table_name="extraction_audit")
    op.drop_index("ix_extraction_audit_alias", table_name="extraction_audit")
    op.drop_table("extraction_audit")

    op.drop_index("ix_dataset_presets_source_kind", table_name="dataset_presets")
    op.drop_index("ix_dataset_presets_namespace", table_name="dataset_presets")
    op.drop_table("dataset_presets")

    for table in ("agent_specs", "model_versions", "strategies"):
        _drop_extraction_columns(table)
