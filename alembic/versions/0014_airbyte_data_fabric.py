"""airbyte data fabric control plane

Revision ID: 0014_airbyte_data_fabric
Revises: 0013_data_engine_expansion
Create Date: 2026-04-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_airbyte_data_fabric"
down_revision = "0013_data_engine_expansion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "airbyte_connectors",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("connector_id", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("runtime", sa.String(length=32), nullable=False, server_default="hybrid"),
        sa.Column("service", sa.String(length=120), nullable=True),
        sa.Column("airbyte_definition_id", sa.String(length=120), nullable=True),
        sa.Column("docker_repository", sa.String(length=240), nullable=True),
        sa.Column("docker_image_tag", sa.String(length=120), nullable=True),
        sa.Column("python_package", sa.String(length=240), nullable=True),
        sa.Column("docs_url", sa.String(length=512), nullable=True),
        sa.Column("config_schema", sa.JSON(), nullable=True),
        sa.Column("streams", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("capabilities", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_airbyte_connectors_connector_id", "airbyte_connectors", ["connector_id"], unique=True)
    op.create_index("ix_airbyte_connectors_kind", "airbyte_connectors", ["kind"])
    op.create_index("ix_airbyte_connectors_runtime", "airbyte_connectors", ["runtime"])
    op.create_index("ix_airbyte_connectors_service", "airbyte_connectors", ["service"])
    op.create_index("ix_airbyte_connectors_airbyte_definition_id", "airbyte_connectors", ["airbyte_definition_id"])

    op.create_table(
        "airbyte_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("source_connector_id", sa.String(length=160), nullable=False),
        sa.Column("destination_connector_id", sa.String(length=160), nullable=False),
        sa.Column("airbyte_source_id", sa.String(length=120), nullable=True),
        sa.Column("airbyte_destination_id", sa.String(length=120), nullable=True),
        sa.Column("airbyte_connection_id", sa.String(length=120), nullable=True),
        sa.Column("namespace", sa.String(length=120), nullable=False, server_default="aqp_airbyte"),
        sa.Column("source_config", sa.JSON(), nullable=True),
        sa.Column("destination_config", sa.JSON(), nullable=True),
        sa.Column("catalog", sa.JSON(), nullable=True),
        sa.Column("streams", sa.JSON(), nullable=True),
        sa.Column("entity_mappings", sa.JSON(), nullable=True),
        sa.Column("materialization_manifest", sa.JSON(), nullable=True),
        sa.Column("schedule", sa.JSON(), nullable=True),
        sa.Column("compute_backend", sa.String(length=32), nullable=False, server_default="auto"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_sync_status", sa.String(length=32), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("namespace", "name", name="uq_airbyte_connections_ns_name"),
        sa.UniqueConstraint("airbyte_connection_id", name="uq_airbyte_connections_airbyte_connection_id"),
    )
    op.create_index("ix_airbyte_connections_name", "airbyte_connections", ["name"])
    op.create_index("ix_airbyte_connections_source_connector_id", "airbyte_connections", ["source_connector_id"])
    op.create_index("ix_airbyte_connections_destination_connector_id", "airbyte_connections", ["destination_connector_id"])
    op.create_index("ix_airbyte_connections_airbyte_source_id", "airbyte_connections", ["airbyte_source_id"])
    op.create_index("ix_airbyte_connections_airbyte_destination_id", "airbyte_connections", ["airbyte_destination_id"])
    op.create_index("ix_airbyte_connections_airbyte_connection_id", "airbyte_connections", ["airbyte_connection_id"], unique=True)
    op.create_index("ix_airbyte_connections_namespace", "airbyte_connections", ["namespace"])
    op.create_index("ix_airbyte_connections_enabled", "airbyte_connections", ["enabled"])
    op.create_index("ix_airbyte_connections_last_sync_status", "airbyte_connections", ["last_sync_status"])
    op.create_index("ix_airbyte_connections_last_sync_at", "airbyte_connections", ["last_sync_at"])

    op.create_table(
        "airbyte_sync_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("connection_id", sa.String(length=36), sa.ForeignKey("airbyte_connections.id", ondelete="SET NULL"), nullable=True),
        sa.Column("pipeline_run_id", sa.String(length=36), sa.ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("manifest_id", sa.String(length=36), sa.ForeignKey("pipeline_manifests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("dataset_id", sa.String(length=36), sa.ForeignKey("dataset_catalogs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("task_id", sa.String(length=120), nullable=True),
        sa.Column("airbyte_job_id", sa.String(length=120), nullable=True),
        sa.Column("airbyte_connection_id", sa.String(length=120), nullable=True),
        sa.Column("runtime", sa.String(length=32), nullable=False, server_default="full_airbyte"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("records_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("streams", sa.JSON(), nullable=True),
        sa.Column("cursor_state", sa.JSON(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_airbyte_sync_runs_connection_id", "airbyte_sync_runs", ["connection_id"])
    op.create_index("ix_airbyte_sync_runs_pipeline_run_id", "airbyte_sync_runs", ["pipeline_run_id"])
    op.create_index("ix_airbyte_sync_runs_manifest_id", "airbyte_sync_runs", ["manifest_id"])
    op.create_index("ix_airbyte_sync_runs_dataset_id", "airbyte_sync_runs", ["dataset_id"])
    op.create_index("ix_airbyte_sync_runs_task_id", "airbyte_sync_runs", ["task_id"])
    op.create_index("ix_airbyte_sync_runs_airbyte_job_id", "airbyte_sync_runs", ["airbyte_job_id"])
    op.create_index("ix_airbyte_sync_runs_airbyte_connection_id", "airbyte_sync_runs", ["airbyte_connection_id"])
    op.create_index("ix_airbyte_sync_runs_runtime", "airbyte_sync_runs", ["runtime"])
    op.create_index("ix_airbyte_sync_runs_status", "airbyte_sync_runs", ["status"])
    op.create_index("ix_airbyte_sync_runs_started_at", "airbyte_sync_runs", ["started_at"])
    op.create_index("ix_airbyte_sync_runs_finished_at", "airbyte_sync_runs", ["finished_at"])
    op.create_index("ix_airbyte_sync_runs_conn_status", "airbyte_sync_runs", ["connection_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_airbyte_sync_runs_conn_status", table_name="airbyte_sync_runs")
    op.drop_index("ix_airbyte_sync_runs_finished_at", table_name="airbyte_sync_runs")
    op.drop_index("ix_airbyte_sync_runs_started_at", table_name="airbyte_sync_runs")
    op.drop_index("ix_airbyte_sync_runs_status", table_name="airbyte_sync_runs")
    op.drop_index("ix_airbyte_sync_runs_runtime", table_name="airbyte_sync_runs")
    op.drop_index("ix_airbyte_sync_runs_airbyte_connection_id", table_name="airbyte_sync_runs")
    op.drop_index("ix_airbyte_sync_runs_airbyte_job_id", table_name="airbyte_sync_runs")
    op.drop_index("ix_airbyte_sync_runs_task_id", table_name="airbyte_sync_runs")
    op.drop_index("ix_airbyte_sync_runs_dataset_id", table_name="airbyte_sync_runs")
    op.drop_index("ix_airbyte_sync_runs_manifest_id", table_name="airbyte_sync_runs")
    op.drop_index("ix_airbyte_sync_runs_pipeline_run_id", table_name="airbyte_sync_runs")
    op.drop_index("ix_airbyte_sync_runs_connection_id", table_name="airbyte_sync_runs")
    op.drop_table("airbyte_sync_runs")

    op.drop_index("ix_airbyte_connections_last_sync_at", table_name="airbyte_connections")
    op.drop_index("ix_airbyte_connections_last_sync_status", table_name="airbyte_connections")
    op.drop_index("ix_airbyte_connections_enabled", table_name="airbyte_connections")
    op.drop_index("ix_airbyte_connections_namespace", table_name="airbyte_connections")
    op.drop_index("ix_airbyte_connections_airbyte_connection_id", table_name="airbyte_connections")
    op.drop_index("ix_airbyte_connections_airbyte_destination_id", table_name="airbyte_connections")
    op.drop_index("ix_airbyte_connections_airbyte_source_id", table_name="airbyte_connections")
    op.drop_index("ix_airbyte_connections_destination_connector_id", table_name="airbyte_connections")
    op.drop_index("ix_airbyte_connections_source_connector_id", table_name="airbyte_connections")
    op.drop_index("ix_airbyte_connections_name", table_name="airbyte_connections")
    op.drop_table("airbyte_connections")

    op.drop_index("ix_airbyte_connectors_airbyte_definition_id", table_name="airbyte_connectors")
    op.drop_index("ix_airbyte_connectors_service", table_name="airbyte_connectors")
    op.drop_index("ix_airbyte_connectors_runtime", table_name="airbyte_connectors")
    op.drop_index("ix_airbyte_connectors_kind", table_name="airbyte_connectors")
    op.drop_index("ix_airbyte_connectors_connector_id", table_name="airbyte_connectors")
    op.drop_table("airbyte_connectors")
