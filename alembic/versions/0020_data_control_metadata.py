"""Add data control metadata/version tables.

Revision ID: 0020_data_control_metadata
Revises: 0019_ownership_enforce
Create Date: 2026-05-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0020_data_control_metadata"
down_revision = "0019_ownership_enforce"
branch_labels = None
depends_on = None


def _project_scope_columns() -> list[sa.Column]:
    return [
        sa.Column("owner_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
    ]


def _project_scope_indexes(table_name: str) -> None:
    op.create_index(f"ix_{table_name}_owner_user_id", table_name, ["owner_user_id"])
    op.create_index(f"ix_{table_name}_workspace_id", table_name, ["workspace_id"])
    op.create_index(f"ix_{table_name}_project_id", table_name, ["project_id"])


def upgrade() -> None:
    op.create_table(
        "source_library_entries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_project_scope_columns(),
        sa.Column("source_id", sa.String(length=36), sa.ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("import_uri", sa.String(length=1024), nullable=True),
        sa.Column("reference_path", sa.String(length=1024), nullable=True),
        sa.Column("docs_url", sa.String(length=1024), nullable=True),
        sa.Column("default_node", sa.String(length=160), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("setup_steps", sa.JSON(), nullable=True),
        sa.Column("pipeline_hints", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "project_id", "source_name", name="uq_source_library_project_source"),
    )
    _project_scope_indexes("source_library_entries")
    op.create_index("ix_source_library_entries_source_id", "source_library_entries", ["source_id"])
    op.create_index("ix_source_library_entries_source_name", "source_library_entries", ["source_name"])
    op.create_index("ix_source_library_entries_enabled", "source_library_entries", ["enabled"])

    op.create_table(
        "source_metadata_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_project_scope_columns(),
        sa.Column("source_id", sa.String(length=36), sa.ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("change_kind", sa.String(length=40), nullable=False, server_default="edit"),
        sa.Column("import_uri", sa.String(length=1024), nullable=True),
        sa.Column("reference_path", sa.String(length=1024), nullable=True),
        sa.Column("docs_url", sa.String(length=1024), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    _project_scope_indexes("source_metadata_versions")
    op.create_index("ix_source_metadata_versions_source_id", "source_metadata_versions", ["source_id"])
    op.create_index("ix_source_metadata_versions_source_name", "source_metadata_versions", ["source_name"])
    op.create_index("ix_source_metadata_versions_change_kind", "source_metadata_versions", ["change_kind"])
    op.create_index("ix_source_metadata_versions_source_version", "source_metadata_versions", ["source_name", "version"])

    op.create_table(
        "dataset_pipeline_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_project_scope_columns(),
        sa.Column("dataset_catalog_id", sa.String(length=36), sa.ForeignKey("dataset_catalogs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("manifest_id", sa.String(length=36), sa.ForeignKey("pipeline_manifests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("sinks", sa.JSON(), nullable=True),
        sa.Column("automations", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "project_id", "name", "version", name="uq_dataset_pipeline_config_version"),
    )
    _project_scope_indexes("dataset_pipeline_configs")
    op.create_index("ix_dataset_pipeline_configs_dataset_catalog_id", "dataset_pipeline_configs", ["dataset_catalog_id"])
    op.create_index("ix_dataset_pipeline_configs_manifest_id", "dataset_pipeline_configs", ["manifest_id"])
    op.create_index("ix_dataset_pipeline_configs_name", "dataset_pipeline_configs", ["name"])
    op.create_index("ix_dataset_pipeline_configs_status", "dataset_pipeline_configs", ["status"])
    op.create_index("ix_dataset_pipeline_configs_is_active", "dataset_pipeline_configs", ["is_active"])
    op.create_index("ix_dataset_pipeline_configs_name_active", "dataset_pipeline_configs", ["name", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_dataset_pipeline_configs_name_active", table_name="dataset_pipeline_configs")
    op.drop_index("ix_dataset_pipeline_configs_is_active", table_name="dataset_pipeline_configs")
    op.drop_index("ix_dataset_pipeline_configs_status", table_name="dataset_pipeline_configs")
    op.drop_index("ix_dataset_pipeline_configs_name", table_name="dataset_pipeline_configs")
    op.drop_index("ix_dataset_pipeline_configs_manifest_id", table_name="dataset_pipeline_configs")
    op.drop_index("ix_dataset_pipeline_configs_dataset_catalog_id", table_name="dataset_pipeline_configs")
    op.drop_index("ix_dataset_pipeline_configs_project_id", table_name="dataset_pipeline_configs")
    op.drop_index("ix_dataset_pipeline_configs_workspace_id", table_name="dataset_pipeline_configs")
    op.drop_index("ix_dataset_pipeline_configs_owner_user_id", table_name="dataset_pipeline_configs")
    op.drop_table("dataset_pipeline_configs")

    op.drop_index("ix_source_metadata_versions_source_version", table_name="source_metadata_versions")
    op.drop_index("ix_source_metadata_versions_change_kind", table_name="source_metadata_versions")
    op.drop_index("ix_source_metadata_versions_source_name", table_name="source_metadata_versions")
    op.drop_index("ix_source_metadata_versions_source_id", table_name="source_metadata_versions")
    op.drop_index("ix_source_metadata_versions_project_id", table_name="source_metadata_versions")
    op.drop_index("ix_source_metadata_versions_workspace_id", table_name="source_metadata_versions")
    op.drop_index("ix_source_metadata_versions_owner_user_id", table_name="source_metadata_versions")
    op.drop_table("source_metadata_versions")

    op.drop_index("ix_source_library_entries_enabled", table_name="source_library_entries")
    op.drop_index("ix_source_library_entries_source_name", table_name="source_library_entries")
    op.drop_index("ix_source_library_entries_source_id", table_name="source_library_entries")
    op.drop_index("ix_source_library_entries_project_id", table_name="source_library_entries")
    op.drop_index("ix_source_library_entries_workspace_id", table_name="source_library_entries")
    op.drop_index("ix_source_library_entries_owner_user_id", table_name="source_library_entries")
    op.drop_table("source_library_entries")
