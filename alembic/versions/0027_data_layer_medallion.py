"""Data layer unification - medallion architecture + active metadata + lineage.

Revision ID: 0027_data_layer_medallion
Revises: 0026_rl_layer
Create Date: 2026-05-08

Threads three concepts through the data plane:

1. **Medallion layering** — every Iceberg table now declares a
   ``medallion_layer`` (``bronze``/``silver``/``gold``) on its
   :class:`aqp.persistence.models.DatasetCatalog` row. The wrapper in
   :mod:`aqp.data.iceberg_catalog` validates that the namespace prefix
   matches the declared layer (``aqp_bronze_*`` / ``aqp_silver_*`` /
   ``aqp_gold_*``).

2. **Active metadata** — :class:`DatasetCatalog` grows
   ``business_metadata`` (data owner, semantic definition, reliability
   score, SLA class) and ``data_contract_json`` (column-level types,
   ranges, required flags). :class:`DatasetVersion` grows
   ``quality_score`` (0..1 roll-up) plus ``quality_breakdown``
   (per-dimension dict).

3. **Lineage events** — new ``data_lineage_events`` table replaces the
   opaque ``PipelineRunRow.lineage`` JSON blob with a queryable graph.
   Edges are ``(source_table_id, target_table_id, transform_kind)``
   tuples; observers wired throughout
   :mod:`aqp.data.iceberg_catalog`,
   :mod:`aqp.data.engine.executor`,
   :mod:`aqp.data.sinks.service`, dbt, and Airbyte fire events through
   :class:`aqp.data.catalog.lineage.LineageWriter`.

Additive only — every column is nullable and every default is safe for
existing rows.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027_data_layer_medallion"
down_revision = "0026_rl_layer"
branch_labels = None
depends_on = None


DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000003"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000004"
DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000005"


def _project_scope_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            server_default=DEFAULT_USER_ID,
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
            server_default=DEFAULT_WORKSPACE_ID,
        ),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
            server_default=DEFAULT_PROJECT_ID,
        ),
    ]


def upgrade() -> None:
    # 1. Medallion + active metadata on DatasetCatalog
    with op.batch_alter_table("dataset_catalogs") as batch:
        batch.add_column(sa.Column("medallion_layer", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("business_metadata", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("data_contract_json", sa.JSON(), nullable=True))
    op.create_index(
        "ix_dataset_catalogs_medallion_layer",
        "dataset_catalogs",
        ["medallion_layer"],
    )

    # 2. Quality scoring on DatasetVersion
    with op.batch_alter_table("dataset_versions") as batch:
        batch.add_column(sa.Column("quality_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("quality_breakdown", sa.JSON(), nullable=True))

    # 3. data_lineage_events — first-class lineage graph
    op.create_table(
        "data_lineage_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_table_id", sa.String(length=240), nullable=True),
        sa.Column("target_table_id", sa.String(length=240), nullable=True),
        sa.Column("transform_kind", sa.String(length=40), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=True),
        sa.Column("actor_kind", sa.String(length=32), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("manifest_id", sa.String(length=36), nullable=True),
        sa.Column("mcp_tool_name", sa.String(length=120), nullable=True),
        sa.Column("service_name", sa.String(length=120), nullable=True),
        sa.Column("rows_written", sa.String(length=32), nullable=True),
        sa.Column("medallion_layer", sa.String(length=16), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        *_project_scope_columns(),
    )
    op.create_index(
        "ix_data_lineage_events_source_table_id",
        "data_lineage_events",
        ["source_table_id"],
    )
    op.create_index(
        "ix_data_lineage_events_target_table_id",
        "data_lineage_events",
        ["target_table_id"],
    )
    op.create_index(
        "ix_data_lineage_events_transform_kind",
        "data_lineage_events",
        ["transform_kind"],
    )
    op.create_index(
        "ix_data_lineage_events_actor",
        "data_lineage_events",
        ["actor"],
    )
    op.create_index(
        "ix_data_lineage_events_actor_kind",
        "data_lineage_events",
        ["actor_kind"],
    )
    op.create_index(
        "ix_data_lineage_events_run_id",
        "data_lineage_events",
        ["run_id"],
    )
    op.create_index(
        "ix_data_lineage_events_manifest_id",
        "data_lineage_events",
        ["manifest_id"],
    )
    op.create_index(
        "ix_data_lineage_events_mcp_tool_name",
        "data_lineage_events",
        ["mcp_tool_name"],
    )
    op.create_index(
        "ix_data_lineage_events_service_name",
        "data_lineage_events",
        ["service_name"],
    )
    op.create_index(
        "ix_data_lineage_events_medallion_layer",
        "data_lineage_events",
        ["medallion_layer"],
    )
    op.create_index(
        "ix_data_lineage_events_created_at",
        "data_lineage_events",
        ["created_at"],
    )
    op.create_index(
        "ix_lineage_source_target",
        "data_lineage_events",
        ["source_table_id", "target_table_id"],
    )
    op.create_index(
        "ix_lineage_kind_created",
        "data_lineage_events",
        ["transform_kind", "created_at"],
    )
    op.create_index(
        "ix_lineage_actor",
        "data_lineage_events",
        ["actor", "actor_kind"],
    )


def downgrade() -> None:
    op.drop_index("ix_lineage_actor", table_name="data_lineage_events")
    op.drop_index("ix_lineage_kind_created", table_name="data_lineage_events")
    op.drop_index("ix_lineage_source_target", table_name="data_lineage_events")
    op.drop_index(
        "ix_data_lineage_events_created_at", table_name="data_lineage_events"
    )
    op.drop_index(
        "ix_data_lineage_events_medallion_layer", table_name="data_lineage_events"
    )
    op.drop_index(
        "ix_data_lineage_events_service_name", table_name="data_lineage_events"
    )
    op.drop_index(
        "ix_data_lineage_events_mcp_tool_name", table_name="data_lineage_events"
    )
    op.drop_index(
        "ix_data_lineage_events_manifest_id", table_name="data_lineage_events"
    )
    op.drop_index("ix_data_lineage_events_run_id", table_name="data_lineage_events")
    op.drop_index(
        "ix_data_lineage_events_actor_kind", table_name="data_lineage_events"
    )
    op.drop_index("ix_data_lineage_events_actor", table_name="data_lineage_events")
    op.drop_index(
        "ix_data_lineage_events_transform_kind",
        table_name="data_lineage_events",
    )
    op.drop_index(
        "ix_data_lineage_events_target_table_id",
        table_name="data_lineage_events",
    )
    op.drop_index(
        "ix_data_lineage_events_source_table_id",
        table_name="data_lineage_events",
    )
    op.drop_table("data_lineage_events")

    with op.batch_alter_table("dataset_versions") as batch:
        batch.drop_column("quality_breakdown")
        batch.drop_column("quality_score")

    op.drop_index(
        "ix_dataset_catalogs_medallion_layer", table_name="dataset_catalogs"
    )
    with op.batch_alter_table("dataset_catalogs") as batch:
        batch.drop_column("data_contract_json")
        batch.drop_column("business_metadata")
        batch.drop_column("medallion_layer")
