"""Data layer expansion: sinks, producers, streaming links, source tags.

Revision ID: 0024_data_layer_expansion
Revises: 0023_merge_data_control_branch
Create Date: 2026-05-03

Adds the persistence layer for the AQP Data Pipelines refactor:

- ``sinks`` and ``sink_versions`` — project-scoped sink registry with
  immutable hash-locked versions, mirroring the bots/agent_specs
  pattern. Lets users plug a saved sink into any pipeline manifest.
- ``market_data_producers`` — control-plane registry of every Kafka-
  bound producer (Alpha-Vantage, IBKR, Alpaca, polygon, synthetic),
  driven by :class:`aqp.streaming.producers.supervisor.ProducerSupervisor`.
- ``streaming_dataset_links`` — many-to-many graph between dataset
  catalogs and Kafka topics / Flink jobs / Airbyte connections / dbt
  models / Dagster assets / producers / sinks.
- Adds ``tags`` JSON and ``version`` Integer to ``data_sources`` so
  versioning + tagging applies uniformly across the data plane.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_data_layer_expansion"
down_revision = "0023_merge_data_control_branch"
branch_labels = None
depends_on = None


# Mirror of aqp.config.defaults so the migration is self-contained.
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


def _project_scope_indexes(table_name: str) -> None:
    op.create_index(f"ix_{table_name}_owner_user_id", table_name, ["owner_user_id"])
    op.create_index(f"ix_{table_name}_workspace_id", table_name, ["workspace_id"])
    op.create_index(f"ix_{table_name}_project_id", table_name, ["project_id"])


def upgrade() -> None:
    op.create_table(
        "sinks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_project_scope_columns(),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column(
            "kind", sa.String(length=64), nullable=False, server_default="iceberg"
        ),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("documentation_url", sa.String(length=1024), nullable=True),
        sa.Column(
            "requires_manifest_node",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "current_version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("annotations", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("project_id", "name", name="uq_sinks_project_name"),
    )
    _project_scope_indexes("sinks")
    op.create_index("ix_sinks_name", "sinks", ["name"])
    op.create_index("ix_sinks_kind", "sinks", ["kind"])
    op.create_index("ix_sinks_enabled", "sinks", ["enabled"])

    op.create_table(
        "sink_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_project_scope_columns(),
        sa.Column(
            "sink_id",
            sa.String(length=36),
            sa.ForeignKey("sinks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("spec_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("sink_id", "spec_hash", name="uq_sink_versions_hash"),
        sa.UniqueConstraint(
            "sink_id", "version", name="uq_sink_versions_version"
        ),
    )
    _project_scope_indexes("sink_versions")
    op.create_index("ix_sink_versions_sink_id", "sink_versions", ["sink_id"])
    op.create_index("ix_sink_versions_spec_hash", "sink_versions", ["spec_hash"])
    op.create_index(
        "ix_sink_versions_sink_version", "sink_versions", ["sink_id", "version"]
    )

    op.create_table(
        "market_data_producers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_project_scope_columns(),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column(
            "kind", sa.String(length=40), nullable=False, server_default="alphavantage"
        ),
        sa.Column(
            "runtime",
            sa.String(length=40),
            nullable=False,
            server_default="kubernetes",
        ),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "deployment_namespace", sa.String(length=120), nullable=True
        ),
        sa.Column("deployment_name", sa.String(length=180), nullable=True),
        sa.Column("image", sa.String(length=512), nullable=True),
        sa.Column("topics", sa.JSON(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("env_overrides", sa.JSON(), nullable=True),
        sa.Column(
            "desired_replicas", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "current_replicas", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "last_status",
            sa.String(length=40),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("last_status_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("annotations", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "project_id", "name", name="uq_market_producers_project_name"
        ),
    )
    _project_scope_indexes("market_data_producers")
    op.create_index(
        "ix_market_data_producers_name", "market_data_producers", ["name"]
    )
    op.create_index(
        "ix_market_data_producers_kind", "market_data_producers", ["kind"]
    )
    op.create_index(
        "ix_market_data_producers_runtime", "market_data_producers", ["runtime"]
    )
    op.create_index(
        "ix_market_data_producers_deployment_namespace",
        "market_data_producers",
        ["deployment_namespace"],
    )
    op.create_index(
        "ix_market_data_producers_deployment_name",
        "market_data_producers",
        ["deployment_name"],
    )
    op.create_index(
        "ix_market_data_producers_last_status",
        "market_data_producers",
        ["last_status"],
    )
    op.create_index(
        "ix_market_data_producers_enabled", "market_data_producers", ["enabled"]
    )
    op.create_index(
        "ix_market_data_producers_kind_status",
        "market_data_producers",
        ["kind", "last_status"],
    )

    op.create_table(
        "streaming_dataset_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_project_scope_columns(),
        sa.Column(
            "dataset_catalog_id",
            sa.String(length=36),
            sa.ForeignKey("dataset_catalogs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("dataset_namespace", sa.String(length=120), nullable=True),
        sa.Column("dataset_table", sa.String(length=240), nullable=True),
        sa.Column(
            "kind",
            sa.String(length=40),
            nullable=False,
            server_default="kafka_topic",
        ),
        sa.Column("target_ref", sa.String(length=512), nullable=False),
        sa.Column("cluster_ref", sa.String(length=240), nullable=True),
        sa.Column(
            "direction",
            sa.String(length=20),
            nullable=False,
            server_default="source",
        ),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("discovered_by", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "dataset_catalog_id",
            "kind",
            "target_ref",
            "direction",
            name="uq_streaming_dataset_links_natural",
        ),
    )
    _project_scope_indexes("streaming_dataset_links")
    op.create_index(
        "ix_streaming_dataset_links_dataset_catalog_id",
        "streaming_dataset_links",
        ["dataset_catalog_id"],
    )
    op.create_index(
        "ix_streaming_dataset_links_dataset_namespace",
        "streaming_dataset_links",
        ["dataset_namespace"],
    )
    op.create_index(
        "ix_streaming_dataset_links_dataset_table",
        "streaming_dataset_links",
        ["dataset_table"],
    )
    op.create_index(
        "ix_streaming_dataset_links_kind", "streaming_dataset_links", ["kind"]
    )
    op.create_index(
        "ix_streaming_dataset_links_target_ref",
        "streaming_dataset_links",
        ["target_ref"],
    )
    op.create_index(
        "ix_streaming_dataset_links_cluster_ref",
        "streaming_dataset_links",
        ["cluster_ref"],
    )
    op.create_index(
        "ix_streaming_dataset_links_direction",
        "streaming_dataset_links",
        ["direction"],
    )
    op.create_index(
        "ix_streaming_dataset_links_enabled",
        "streaming_dataset_links",
        ["enabled"],
    )
    op.create_index(
        "ix_streaming_dataset_links_lookup",
        "streaming_dataset_links",
        ["kind", "target_ref"],
    )

    # data_sources: add tags + version columns
    with op.batch_alter_table("data_sources") as batch:
        batch.add_column(sa.Column("tags", sa.JSON(), nullable=True))
        batch.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default="1")
        )


def downgrade() -> None:
    with op.batch_alter_table("data_sources") as batch:
        batch.drop_column("version")
        batch.drop_column("tags")

    op.drop_index(
        "ix_streaming_dataset_links_lookup", table_name="streaming_dataset_links"
    )
    op.drop_index(
        "ix_streaming_dataset_links_enabled", table_name="streaming_dataset_links"
    )
    op.drop_index(
        "ix_streaming_dataset_links_direction", table_name="streaming_dataset_links"
    )
    op.drop_index(
        "ix_streaming_dataset_links_cluster_ref", table_name="streaming_dataset_links"
    )
    op.drop_index(
        "ix_streaming_dataset_links_target_ref", table_name="streaming_dataset_links"
    )
    op.drop_index(
        "ix_streaming_dataset_links_kind", table_name="streaming_dataset_links"
    )
    op.drop_index(
        "ix_streaming_dataset_links_dataset_table", table_name="streaming_dataset_links"
    )
    op.drop_index(
        "ix_streaming_dataset_links_dataset_namespace",
        table_name="streaming_dataset_links",
    )
    op.drop_index(
        "ix_streaming_dataset_links_dataset_catalog_id",
        table_name="streaming_dataset_links",
    )
    op.drop_index(
        "ix_streaming_dataset_links_project_id", table_name="streaming_dataset_links"
    )
    op.drop_index(
        "ix_streaming_dataset_links_workspace_id",
        table_name="streaming_dataset_links",
    )
    op.drop_index(
        "ix_streaming_dataset_links_owner_user_id",
        table_name="streaming_dataset_links",
    )
    op.drop_table("streaming_dataset_links")

    op.drop_index(
        "ix_market_data_producers_kind_status", table_name="market_data_producers"
    )
    op.drop_index(
        "ix_market_data_producers_enabled", table_name="market_data_producers"
    )
    op.drop_index(
        "ix_market_data_producers_last_status", table_name="market_data_producers"
    )
    op.drop_index(
        "ix_market_data_producers_deployment_name", table_name="market_data_producers"
    )
    op.drop_index(
        "ix_market_data_producers_deployment_namespace",
        table_name="market_data_producers",
    )
    op.drop_index(
        "ix_market_data_producers_runtime", table_name="market_data_producers"
    )
    op.drop_index(
        "ix_market_data_producers_kind", table_name="market_data_producers"
    )
    op.drop_index(
        "ix_market_data_producers_name", table_name="market_data_producers"
    )
    op.drop_index(
        "ix_market_data_producers_project_id", table_name="market_data_producers"
    )
    op.drop_index(
        "ix_market_data_producers_workspace_id", table_name="market_data_producers"
    )
    op.drop_index(
        "ix_market_data_producers_owner_user_id", table_name="market_data_producers"
    )
    op.drop_table("market_data_producers")

    op.drop_index("ix_sink_versions_sink_version", table_name="sink_versions")
    op.drop_index("ix_sink_versions_spec_hash", table_name="sink_versions")
    op.drop_index("ix_sink_versions_sink_id", table_name="sink_versions")
    op.drop_index("ix_sink_versions_project_id", table_name="sink_versions")
    op.drop_index("ix_sink_versions_workspace_id", table_name="sink_versions")
    op.drop_index("ix_sink_versions_owner_user_id", table_name="sink_versions")
    op.drop_table("sink_versions")

    op.drop_index("ix_sinks_enabled", table_name="sinks")
    op.drop_index("ix_sinks_kind", table_name="sinks")
    op.drop_index("ix_sinks_name", table_name="sinks")
    op.drop_index("ix_sinks_project_id", table_name="sinks")
    op.drop_index("ix_sinks_workspace_id", table_name="sinks")
    op.drop_index("ix_sinks_owner_user_id", table_name="sinks")
    op.drop_table("sinks")
