"""Bipartite lineage graph: dataset_vertex + transform_vertex + edge.

Revision ID: 0059_lineage_graph_v2
Revises: 0058_bot_event_sourcing
Create Date: 2026-05-24

Workstream A of the AQP Data Layer Selective Additive Enhancement.

Adds three new lineage tables that sit alongside the existing flat
``data_lineage_events`` log (untouched):

- ``lineage_dataset_vertex`` — content-addressed dataset snapshots
  (Iceberg manifest + snapshot id, or fallback SHA-256 over URI +
  params for non-Iceberg backends).
- ``lineage_transform_vertex`` — one row per data motion. Signature +
  signing_key_id columns are nullable from day one so workstream C
  signing can opt-in without a schema change.
- ``lineage_edge`` — directed edge (``consumes`` / ``produces``)
  between vertices.

Tenancy / governance hooks (AGENTS rules):

- Every row carries ``owner_user_id`` / ``workspace_id`` /
  ``project_id`` (ProjectScopedMixin columns).
- The legacy ``data_lineage_events`` table is untouched so the
  rollback runbook is a one-toggle flip of
  ``AQP_LINEAGE_GRAPH_ENABLED=false``.

AGENTS rule 6: this migration is immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0059_lineage_graph_v2"
down_revision = "0058_bot_event_sourcing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # lineage_dataset_vertex
    # ------------------------------------------------------------------
    op.create_table(
        "lineage_dataset_vertex",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("namespace", sa.String(120), nullable=False, index=True),
        sa.Column("name", sa.String(240), nullable=False, index=True),
        sa.Column("content_hash", sa.String(64), nullable=False, index=True),
        sa.Column("iceberg_snapshot_id", sa.BigInteger, nullable=True),
        sa.Column("manifest_list_location", sa.Text, nullable=True),
        sa.Column("schema_facet", sa.JSON, nullable=True),
        sa.Column("row_count", sa.BigInteger, nullable=True),
        sa.Column("byte_size", sa.BigInteger, nullable=True),
        sa.Column("medallion_layer", sa.String(16), nullable=True),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "namespace", "name", "content_hash", name="uq_lineage_dataset_vertex_addr"
        ),
    )
    op.create_index(
        "ix_lineage_dataset_vertex_ns_name",
        "lineage_dataset_vertex",
        ["namespace", "name"],
    )
    op.create_index(
        "ix_lineage_dataset_vertex_snapshot",
        "lineage_dataset_vertex",
        ["iceberg_snapshot_id"],
    )
    op.create_index(
        "ix_lineage_dataset_vertex_created",
        "lineage_dataset_vertex",
        ["created_at"],
    )
    op.create_index(
        "ix_lineage_dataset_vertex_layer",
        "lineage_dataset_vertex",
        ["medallion_layer"],
    )
    op.create_index(
        "ix_lineage_dataset_vertex_workspace",
        "lineage_dataset_vertex",
        ["workspace_id"],
    )

    # ------------------------------------------------------------------
    # lineage_transform_vertex
    # ------------------------------------------------------------------
    op.create_table(
        "lineage_transform_vertex",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_name", sa.String(240), nullable=False, index=True),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("code_version", sa.String(120), nullable=True),
        sa.Column("transform_kind", sa.String(40), nullable=False),
        sa.Column("parameters", sa.JSON, nullable=True),
        sa.Column("actor", sa.String(120), nullable=True),
        sa.Column("actor_kind", sa.String(32), nullable=True),
        sa.Column("service_name", sa.String(120), nullable=True),
        sa.Column("mcp_tool_name", sa.String(120), nullable=True),
        sa.Column("rows_written", sa.BigInteger, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        # Workstream C — signature columns. Nullable so deployments
        # with ``lineage_signing_enabled=false`` still insert rows.
        sa.Column("signature", sa.Text, nullable=True),
        sa.Column("signing_key_id", sa.String(96), nullable=True),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "started_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime, nullable=True),
    )
    op.create_index(
        "ix_lineage_transform_vertex_run", "lineage_transform_vertex", ["run_id"]
    )
    op.create_index(
        "ix_lineage_transform_vertex_kind_started",
        "lineage_transform_vertex",
        ["transform_kind", "started_at"],
    )
    op.create_index(
        "ix_lineage_transform_vertex_actor",
        "lineage_transform_vertex",
        ["actor", "actor_kind"],
    )
    op.create_index(
        "ix_lineage_transform_vertex_mcp_tool",
        "lineage_transform_vertex",
        ["mcp_tool_name"],
    )
    op.create_index(
        "ix_lineage_transform_vertex_signing_key",
        "lineage_transform_vertex",
        ["signing_key_id"],
    )
    op.create_index(
        "ix_lineage_transform_vertex_workspace",
        "lineage_transform_vertex",
        ["workspace_id"],
    )

    # ------------------------------------------------------------------
    # lineage_edge
    # ------------------------------------------------------------------
    op.create_table(
        "lineage_edge",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("from_vertex", sa.String(36), nullable=False, index=True),
        sa.Column("to_vertex", sa.String(36), nullable=False, index=True),
        sa.Column("edge_type", sa.String(16), nullable=False),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "from_vertex", "to_vertex", "edge_type", name="uq_lineage_edge_triple"
        ),
    )
    op.create_index("ix_lineage_edge_type", "lineage_edge", ["edge_type"])
    op.create_index("ix_lineage_edge_created", "lineage_edge", ["created_at"])
    op.create_index(
        "ix_lineage_edge_to_from", "lineage_edge", ["to_vertex", "from_vertex"]
    )
    op.create_index(
        "ix_lineage_edge_workspace", "lineage_edge", ["workspace_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_lineage_edge_workspace", table_name="lineage_edge")
    op.drop_index("ix_lineage_edge_to_from", table_name="lineage_edge")
    op.drop_index("ix_lineage_edge_created", table_name="lineage_edge")
    op.drop_index("ix_lineage_edge_type", table_name="lineage_edge")
    op.drop_table("lineage_edge")

    op.drop_index(
        "ix_lineage_transform_vertex_workspace",
        table_name="lineage_transform_vertex",
    )
    op.drop_index(
        "ix_lineage_transform_vertex_signing_key",
        table_name="lineage_transform_vertex",
    )
    op.drop_index(
        "ix_lineage_transform_vertex_mcp_tool",
        table_name="lineage_transform_vertex",
    )
    op.drop_index(
        "ix_lineage_transform_vertex_actor",
        table_name="lineage_transform_vertex",
    )
    op.drop_index(
        "ix_lineage_transform_vertex_kind_started",
        table_name="lineage_transform_vertex",
    )
    op.drop_index(
        "ix_lineage_transform_vertex_run", table_name="lineage_transform_vertex"
    )
    op.drop_table("lineage_transform_vertex")

    op.drop_index(
        "ix_lineage_dataset_vertex_workspace", table_name="lineage_dataset_vertex"
    )
    op.drop_index(
        "ix_lineage_dataset_vertex_layer", table_name="lineage_dataset_vertex"
    )
    op.drop_index(
        "ix_lineage_dataset_vertex_created", table_name="lineage_dataset_vertex"
    )
    op.drop_index(
        "ix_lineage_dataset_vertex_snapshot", table_name="lineage_dataset_vertex"
    )
    op.drop_index(
        "ix_lineage_dataset_vertex_ns_name", table_name="lineage_dataset_vertex"
    )
    op.drop_table("lineage_dataset_vertex")
