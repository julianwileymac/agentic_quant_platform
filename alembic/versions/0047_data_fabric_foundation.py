"""Data fabric foundation: instrument catalog, feed edges, ingestion ledger,
fabric version snapshots, and DataSource extension columns.

Revision ID: 0047_data_fabric_foundation
Revises: 0046_workflow_versioning
Create Date: 2026-05-17
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision = "0047_data_fabric_foundation"
down_revision = "0046_workflow_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create the enum type first so the table can reference it.
    ingestion_status = postgresql.ENUM(
        "PENDING",
        "RUNNING",
        "SUCCESS",
        "PARTIAL_FAILURE",
        "FATAL_ERROR",
        name="ingestion_execution_status_enum",
        create_type=False,
    )
    ingestion_status.create(op.get_bind(), checkfirst=True)

    # 2. instrument_catalogs
    op.create_table(
        "instrument_catalogs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("universal_ticker", sa.String(length=50), nullable=False, index=True),
        sa.Column("asset_class", sa.String(length=50), nullable=False, index=True),
        sa.Column("exchange_code", sa.String(length=50), nullable=True, index=True),
        sa.Column("metadata_blob", postgresql.JSONB(), nullable=True),
        sa.Column(
            "is_actively_traded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("last_catalog_sync", sa.DateTime(timezone=False), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "promoted_instrument_id",
            sa.String(length=36),
            sa.ForeignKey("instruments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "universal_ticker",
            "exchange_code",
            name="uq_instrument_catalog_ticker_exchange",
        ),
    )
    op.create_index(
        "ix_instrument_catalog_asset_class_exchange",
        "instrument_catalogs",
        ["asset_class", "exchange_code"],
    )
    op.create_index(
        "ix_instrument_catalog_metadata_gin",
        "instrument_catalogs",
        ["metadata_blob"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_instrument_catalog_metadata_sector",
        "instrument_catalogs",
        [sa.text("(metadata_blob->>'sector')")],
    )

    # 3. catalog_feed_edges
    op.create_table(
        "catalog_feed_edges",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "instrument_catalog_id",
            sa.String(length=36),
            sa.ForeignKey("instrument_catalogs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "data_source_id",
            sa.String(length=36),
            sa.ForeignKey("data_sources.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "provider_specific_ticker",
            sa.String(length=100),
            nullable=False,
            index=True,
        ),
        sa.Column("edge_metadata_params", postgresql.JSONB(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "instrument_catalog_id",
            "data_source_id",
            "provider_specific_ticker",
            name="uq_catalog_feed_edge",
        ),
    )

    # 4. ingestion_ledger
    op.create_table(
        "ingestion_ledger",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("fabric_uuid", sa.String(length=36), nullable=False, index=True),
        sa.Column(
            "data_source_id",
            sa.String(length=36),
            sa.ForeignKey("data_sources.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "fetcher_run_id",
            sa.String(length=36),
            sa.ForeignKey("fetcher_runs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("request_hash", sa.String(length=64), nullable=False, index=True),
        sa.Column("requested_time_window", sa.String(length=100), nullable=True),
        sa.Column(
            "execution_start",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("execution_end", sa.DateTime(timezone=False), nullable=True),
        sa.Column("records_extracted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_persisted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "execution_status",
            postgresql.ENUM(name="ingestion_execution_status_enum", create_type=False),
            nullable=False,
            server_default="PENDING",
            index=True,
        ),
        sa.Column("error_traceback", sa.Text(), nullable=True),
        sa.Column("otel_trace_id", sa.String(length=32), nullable=True),
        sa.Column("otel_span_id", sa.String(length=16), nullable=True),
        sa.Column("lineage_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("business_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "ix_ingestion_ledger_request_hash_status",
        "ingestion_ledger",
        ["request_hash", "execution_status"],
    )
    op.create_index(
        "ix_ingestion_ledger_data_source_started",
        "ingestion_ledger",
        ["data_source_id", "execution_start"],
    )

    # 5. fabric_version_snapshots
    op.create_table(
        "fabric_version_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("fabric_uuid", sa.String(length=36), nullable=False, index=True),
        sa.Column("object_kind", sa.String(length=64), nullable=False, index=True),
        sa.Column("version_vector", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot_data", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_fabric_version_snapshots_uuid_created",
        "fabric_version_snapshots",
        ["fabric_uuid", "created_at"],
    )

    # 6. DataSource extension columns
    op.add_column(
        "data_sources",
        sa.Column("loader_class_path", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "data_sources",
        sa.Column("rate_limit_params", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "data_sources",
        sa.Column("execution_schedule", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("data_sources", "execution_schedule")
    op.drop_column("data_sources", "rate_limit_params")
    op.drop_column("data_sources", "loader_class_path")

    op.drop_index(
        "ix_fabric_version_snapshots_uuid_created",
        table_name="fabric_version_snapshots",
    )
    op.drop_table("fabric_version_snapshots")

    op.drop_index("ix_ingestion_ledger_data_source_started", table_name="ingestion_ledger")
    op.drop_index("ix_ingestion_ledger_request_hash_status", table_name="ingestion_ledger")
    op.drop_table("ingestion_ledger")

    op.drop_table("catalog_feed_edges")

    op.drop_index("ix_instrument_catalog_metadata_sector", table_name="instrument_catalogs")
    op.drop_index("ix_instrument_catalog_metadata_gin", table_name="instrument_catalogs")
    op.drop_index(
        "ix_instrument_catalog_asset_class_exchange",
        table_name="instrument_catalogs",
    )
    op.drop_table("instrument_catalogs")

    postgresql.ENUM(name="ingestion_execution_status_enum").drop(
        op.get_bind(),
        checkfirst=True,
    )
