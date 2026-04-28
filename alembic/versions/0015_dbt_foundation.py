"""dbt foundation metadata tables

Revision ID: 0015_dbt_foundation
Revises: 0014_airbyte_data_fabric
Create Date: 2026-04-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_dbt_foundation"
down_revision = "0014_airbyte_data_fabric"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dbt_projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("project_dir", sa.String(length=1024), nullable=False),
        sa.Column("profiles_dir", sa.String(length=1024), nullable=False),
        sa.Column("target", sa.String(length=80), nullable=False, server_default="dev"),
        sa.Column("adapter", sa.String(length=80), nullable=False, server_default="duckdb"),
        sa.Column("duckdb_path", sa.String(length=1024), nullable=True),
        sa.Column("generated_schema", sa.String(length=120), nullable=True),
        sa.Column("generated_tag", sa.String(length=120), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", "project_dir", name="uq_dbt_projects_name_dir"),
    )
    op.create_index("ix_dbt_projects_name", "dbt_projects", ["name"])
    op.create_index("ix_dbt_projects_target", "dbt_projects", ["target"])
    op.create_index("ix_dbt_projects_adapter", "dbt_projects", ["adapter"])
    op.create_index("ix_dbt_projects_enabled", "dbt_projects", ["enabled"])

    op.create_table(
        "dbt_model_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("dbt_projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("unique_id", sa.String(length=512), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("package_name", sa.String(length=160), nullable=True),
        sa.Column("original_file_path", sa.String(length=1024), nullable=True),
        sa.Column("database", sa.String(length=240), nullable=True),
        sa.Column("schema", sa.String(length=240), nullable=True),
        sa.Column("alias", sa.String(length=240), nullable=True),
        sa.Column("materialized", sa.String(length=64), nullable=True),
        sa.Column("checksum", sa.String(length=120), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("depends_on", sa.JSON(), nullable=True),
        sa.Column("columns", sa.JSON(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_dbt_model_versions_project_id", "dbt_model_versions", ["project_id"])
    op.create_index("ix_dbt_model_versions_unique_id", "dbt_model_versions", ["unique_id"])
    op.create_index("ix_dbt_model_versions_name", "dbt_model_versions", ["name"])
    op.create_index("ix_dbt_model_versions_resource_type", "dbt_model_versions", ["resource_type"])
    op.create_index("ix_dbt_model_versions_checksum", "dbt_model_versions", ["checksum"])
    op.create_index("ix_dbt_model_versions_lookup", "dbt_model_versions", ["project_id", "unique_id"])

    op.create_table(
        "dbt_source_mappings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("dbt_projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("dbt_unique_id", sa.String(length=512), nullable=False),
        sa.Column("source_kind", sa.String(length=80), nullable=False),
        sa.Column("source_name", sa.String(length=512), nullable=False),
        sa.Column("dataset_catalog_id", sa.String(length=36), sa.ForeignKey("dataset_catalogs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("iceberg_identifier", sa.String(length=240), nullable=True),
        sa.Column("storage_uri", sa.String(length=1024), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "dbt_unique_id", "source_kind", "source_name", name="uq_dbt_source_mapping"),
    )
    op.create_index("ix_dbt_source_mappings_project_id", "dbt_source_mappings", ["project_id"])
    op.create_index("ix_dbt_source_mappings_dbt_unique_id", "dbt_source_mappings", ["dbt_unique_id"])
    op.create_index("ix_dbt_source_mappings_source_kind", "dbt_source_mappings", ["source_kind"])
    op.create_index("ix_dbt_source_mappings_source_name", "dbt_source_mappings", ["source_name"])
    op.create_index("ix_dbt_source_mappings_dataset_catalog_id", "dbt_source_mappings", ["dataset_catalog_id"])
    op.create_index("ix_dbt_source_mappings_iceberg_identifier", "dbt_source_mappings", ["iceberg_identifier"])

    op.create_table(
        "dbt_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("dbt_projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("command", sa.String(length=80), nullable=False),
        sa.Column("selector", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("artifacts", sa.JSON(), nullable=True),
        sa.Column("args", sa.JSON(), nullable=True),
        sa.Column("run_results", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("models_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("triggered_by", sa.String(length=120), nullable=True),
    )
    op.create_index("ix_dbt_runs_project_id", "dbt_runs", ["project_id"])
    op.create_index("ix_dbt_runs_command", "dbt_runs", ["command"])
    op.create_index("ix_dbt_runs_status", "dbt_runs", ["status"])
    op.create_index("ix_dbt_runs_success", "dbt_runs", ["success"])
    op.create_index("ix_dbt_runs_started_at", "dbt_runs", ["started_at"])
    op.create_index("ix_dbt_runs_finished_at", "dbt_runs", ["finished_at"])
    op.create_index("ix_dbt_runs_triggered_by", "dbt_runs", ["triggered_by"])


def downgrade() -> None:
    op.drop_index("ix_dbt_runs_triggered_by", table_name="dbt_runs")
    op.drop_index("ix_dbt_runs_finished_at", table_name="dbt_runs")
    op.drop_index("ix_dbt_runs_started_at", table_name="dbt_runs")
    op.drop_index("ix_dbt_runs_success", table_name="dbt_runs")
    op.drop_index("ix_dbt_runs_status", table_name="dbt_runs")
    op.drop_index("ix_dbt_runs_command", table_name="dbt_runs")
    op.drop_index("ix_dbt_runs_project_id", table_name="dbt_runs")
    op.drop_table("dbt_runs")

    op.drop_index("ix_dbt_source_mappings_iceberg_identifier", table_name="dbt_source_mappings")
    op.drop_index("ix_dbt_source_mappings_dataset_catalog_id", table_name="dbt_source_mappings")
    op.drop_index("ix_dbt_source_mappings_source_name", table_name="dbt_source_mappings")
    op.drop_index("ix_dbt_source_mappings_source_kind", table_name="dbt_source_mappings")
    op.drop_index("ix_dbt_source_mappings_dbt_unique_id", table_name="dbt_source_mappings")
    op.drop_index("ix_dbt_source_mappings_project_id", table_name="dbt_source_mappings")
    op.drop_table("dbt_source_mappings")

    op.drop_index("ix_dbt_model_versions_lookup", table_name="dbt_model_versions")
    op.drop_index("ix_dbt_model_versions_checksum", table_name="dbt_model_versions")
    op.drop_index("ix_dbt_model_versions_resource_type", table_name="dbt_model_versions")
    op.drop_index("ix_dbt_model_versions_name", table_name="dbt_model_versions")
    op.drop_index("ix_dbt_model_versions_unique_id", table_name="dbt_model_versions")
    op.drop_index("ix_dbt_model_versions_project_id", table_name="dbt_model_versions")
    op.drop_table("dbt_model_versions")

    op.drop_index("ix_dbt_projects_enabled", table_name="dbt_projects")
    op.drop_index("ix_dbt_projects_adapter", table_name="dbt_projects")
    op.drop_index("ix_dbt_projects_target", table_name="dbt_projects")
    op.drop_index("ix_dbt_projects_name", table_name="dbt_projects")
    op.drop_table("dbt_projects")
