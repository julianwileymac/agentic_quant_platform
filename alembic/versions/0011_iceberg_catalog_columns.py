"""iceberg-first catalog columns

Revision ID: 0011_iceberg_catalog_columns
Revises: 0010_feature_sets_equity_reports
Create Date: 2026-04-26

Extends ``dataset_catalogs`` with the columns needed to mirror Iceberg
tables: ``iceberg_identifier`` (the ``namespace.table`` reference into
the PyIceberg catalog), ``load_mode`` (managed | lazy), ``source_uri``
(original on-disk / object-store path), ``llm_annotations`` (JSON blob
emitted by the annotation step), and ``column_docs`` (JSON list of
per-column descriptions).

All new columns are nullable / default-friendly so existing OHLCV bar
catalog rows survive untouched.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_iceberg_catalog_columns"
down_revision = "0010_feature_sets_equity_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dataset_catalogs",
        sa.Column("iceberg_identifier", sa.String(length=240), nullable=True),
    )
    op.add_column(
        "dataset_catalogs",
        sa.Column(
            "load_mode",
            sa.String(length=32),
            nullable=False,
            server_default="managed",
        ),
    )
    op.add_column(
        "dataset_catalogs",
        sa.Column("source_uri", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "dataset_catalogs",
        sa.Column("llm_annotations", sa.JSON(), nullable=True),
    )
    op.add_column(
        "dataset_catalogs",
        sa.Column("column_docs", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_dataset_catalogs_iceberg_identifier",
        "dataset_catalogs",
        ["iceberg_identifier"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dataset_catalogs_iceberg_identifier",
        table_name="dataset_catalogs",
    )
    op.drop_column("dataset_catalogs", "column_docs")
    op.drop_column("dataset_catalogs", "llm_annotations")
    op.drop_column("dataset_catalogs", "source_uri")
    op.drop_column("dataset_catalogs", "load_mode")
    op.drop_column("dataset_catalogs", "iceberg_identifier")
