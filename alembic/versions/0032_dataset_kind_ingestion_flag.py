"""Self-service data fabric phase 0 — dataset kind + ingestion flag.

Revision ID: 0032_dataset_kind_ingestion_flag
Revises: 0031_analysis_layer
Create Date: 2026-05-09

Extends :class:`aqp.persistence.models.DatasetCatalog` with four
columns that back the new self-service catalog primitives:

- ``dataset_kind`` — registered alias from
  :func:`aqp.data.datasets.register_dataset_kind` (``iceberg``,
  ``parquet``, ``api``, ``partitioned``, ``sql``, ``redis_kv``,
  ``csv``, ``external``).
- ``is_ingested`` — discovery-browser lifecycle flag. ``true`` for
  rows that have a materialised payload, ``false`` for
  "discovered but not yet ingested" external entries.
- ``spec_hash`` — sha256 over the canonical
  :class:`aqp.data.datasets.DatasetSpec` so drift between two rows is
  visible without loading payload bytes.
- ``external_spec_json`` — descriptor for uningested entries (URI,
  docs URL, suggested connector kind, intent metadata).

Backfill: rows with a non-null ``iceberg_identifier`` are flagged
``dataset_kind='iceberg'`` and ``is_ingested=true``. Everything else
is left null so legacy rows surface in the discovery browser as
"unclassified" and the operator can promote them.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0032_dataset_kind_ingestion_flag"
down_revision = "0031_analysis_layer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dataset_catalogs",
        sa.Column("dataset_kind", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "dataset_catalogs",
        sa.Column("is_ingested", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "dataset_catalogs",
        sa.Column("spec_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "dataset_catalogs",
        sa.Column("external_spec_json", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_dataset_catalogs_dataset_kind",
        "dataset_catalogs",
        ["dataset_kind"],
    )
    op.create_index(
        "ix_dataset_catalogs_is_ingested",
        "dataset_catalogs",
        ["is_ingested"],
    )
    op.create_index(
        "ix_dataset_catalogs_spec_hash",
        "dataset_catalogs",
        ["spec_hash"],
    )

    # Backfill: every legacy row with an iceberg identifier is, by
    # definition, an "ingested iceberg dataset". Run separately so it
    # works against both Postgres and SQLite (test runs).
    op.execute(
        """
        UPDATE dataset_catalogs
           SET dataset_kind = 'iceberg',
               is_ingested  = TRUE
         WHERE iceberg_identifier IS NOT NULL
           AND dataset_kind IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dataset_catalogs_spec_hash", table_name="dataset_catalogs"
    )
    op.drop_index(
        "ix_dataset_catalogs_is_ingested", table_name="dataset_catalogs"
    )
    op.drop_index(
        "ix_dataset_catalogs_dataset_kind", table_name="dataset_catalogs"
    )
    op.drop_column("dataset_catalogs", "external_spec_json")
    op.drop_column("dataset_catalogs", "spec_hash")
    op.drop_column("dataset_catalogs", "is_ingested")
    op.drop_column("dataset_catalogs", "dataset_kind")
