"""data fabric engine expansion

Revision ID: 0013_data_engine_expansion
Revises: 0012_agents_rag_memory
Create Date: 2026-04-28

Single migration that lands the Phase 3 + Phase 4 schema for the data
fabric expansion:

- ``dataset_catalogs`` gains ``compute_backend``, ``dagster_asset_key``,
  ``datahub_urn``, ``entity_extraction_status``, ``manifest_id``,
  ``pipeline_kind``.
- ``dataset_versions`` gains ``materialization_engine``,
  ``dagster_run_id``, ``partition_key``, ``code_version_sha``.
- ``data_sources`` gains ``kind_subtype``, ``transport``,
  ``rate_limit_json``, ``pagination_json``, ``endpoints_json``,
  ``health_status``, ``last_probe_at``.
- New tables: ``pipeline_manifests``, ``pipeline_runs``,
  ``dataset_profiles``, ``datahub_sync_log``, ``fetcher_runs``,
  ``entities``, ``entity_identifiers``, ``entity_relations``,
  ``entity_annotations``, ``entity_dataset_links``.

All new columns are nullable / default-friendly so existing rows
survive untouched.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_data_engine_expansion"
down_revision = "0012_agents_rag_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----------------------------------------------------- dataset_catalogs
    op.add_column(
        "dataset_catalogs",
        sa.Column("compute_backend", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "dataset_catalogs",
        sa.Column("dagster_asset_key", sa.String(length=240), nullable=True),
    )
    op.add_column(
        "dataset_catalogs",
        sa.Column("datahub_urn", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "dataset_catalogs",
        sa.Column(
            "entity_extraction_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "dataset_catalogs",
        sa.Column("manifest_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "dataset_catalogs",
        sa.Column("pipeline_kind", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_dataset_catalogs_dagster_asset_key",
        "dataset_catalogs",
        ["dagster_asset_key"],
    )
    op.create_index(
        "ix_dataset_catalogs_datahub_urn",
        "dataset_catalogs",
        ["datahub_urn"],
    )

    # ----------------------------------------------------- dataset_versions
    op.add_column(
        "dataset_versions",
        sa.Column("materialization_engine", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "dataset_versions",
        sa.Column("dagster_run_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "dataset_versions",
        sa.Column("partition_key", sa.String(length=240), nullable=True),
    )
    op.add_column(
        "dataset_versions",
        sa.Column("code_version_sha", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_dataset_versions_dagster_run_id",
        "dataset_versions",
        ["dagster_run_id"],
    )

    # --------------------------------------------------------- data_sources
    op.add_column(
        "data_sources",
        sa.Column("kind_subtype", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "data_sources",
        sa.Column("transport", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "data_sources",
        sa.Column("rate_limit_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "data_sources",
        sa.Column("pagination_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "data_sources",
        sa.Column("endpoints_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "data_sources",
        sa.Column(
            "health_status",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "data_sources",
        sa.Column("last_probe_at", sa.DateTime(), nullable=True),
    )

    # ----------------------------------------------------- pipeline_manifests
    op.create_table(
        "pipeline_manifests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "namespace",
            sa.String(length=120),
            nullable=False,
            server_default="aqp",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner", sa.String(length=120), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("spec_json", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("compute_backend", sa.String(length=32), nullable=True),
        sa.Column("schedule_cron", sa.String(length=120), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_status", sa.String(length=32), nullable=True),
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
        sa.UniqueConstraint("namespace", "name", name="uq_pipeline_manifests_ns_name"),
    )
    op.create_index("ix_pipeline_manifests_name", "pipeline_manifests", ["name"])
    op.create_index(
        "ix_pipeline_manifests_namespace", "pipeline_manifests", ["namespace"]
    )
    op.create_index(
        "ix_pipeline_manifests_enabled", "pipeline_manifests", ["enabled"]
    )

    # --------------------------------------------------------- pipeline_runs
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "manifest_id",
            sa.String(length=36),
            sa.ForeignKey("pipeline_manifests.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "namespace",
            sa.String(length=120),
            nullable=False,
            server_default="aqp",
        ),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "backend",
            sa.String(length=32),
            nullable=False,
            server_default="local",
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="running",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column(
            "rows_written", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "tables_written", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("sink_result", sa.JSON(), nullable=True),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column("errors", sa.JSON(), nullable=True),
        sa.Column("extras", sa.JSON(), nullable=True),
        sa.Column("triggered_by", sa.String(length=120), nullable=True),
        sa.Column("dagster_run_id", sa.String(length=120), nullable=True),
        sa.Column("code_version_sha", sa.String(length=64), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
    )
    op.create_index("ix_pipeline_runs_manifest_id", "pipeline_runs", ["manifest_id"])
    op.create_index("ix_pipeline_runs_namespace", "pipeline_runs", ["namespace"])
    op.create_index("ix_pipeline_runs_status", "pipeline_runs", ["status"])
    op.create_index("ix_pipeline_runs_started_at", "pipeline_runs", ["started_at"])

    # ------------------------------------------------------ dataset_profiles
    op.create_table(
        "dataset_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("namespace", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("columns", sa.JSON(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("engine", sa.String(length=32), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_dataset_profiles_namespace", "dataset_profiles", ["namespace"])
    op.create_index("ix_dataset_profiles_name", "dataset_profiles", ["name"])
    op.create_index(
        "ix_dataset_profiles_lookup",
        "dataset_profiles",
        ["namespace", "name", "version"],
    )

    # ----------------------------------------------------- datahub_sync_log
    op.create_table(
        "datahub_sync_log",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "direction",
            sa.String(length=16),
            nullable=False,
            server_default="push",
        ),
        sa.Column("target", sa.String(length=240), nullable=False),
        sa.Column("urn", sa.String(length=512), nullable=True),
        sa.Column("platform", sa.String(length=64), nullable=True),
        sa.Column("platform_instance", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="ok",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_datahub_sync_log_target", "datahub_sync_log", ["target"])
    op.create_index("ix_datahub_sync_log_status", "datahub_sync_log", ["status"])
    op.create_index("ix_datahub_sync_log_started", "datahub_sync_log", ["started_at"])

    # --------------------------------------------------------- fetcher_runs
    op.create_table(
        "fetcher_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("fetcher_alias", sa.String(length=160), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column(
            "rows_produced", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "bytes_received", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="ok",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "pipeline_run_id",
            sa.String(length=36),
            sa.ForeignKey("pipeline_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("extras", sa.JSON(), nullable=True),
    )
    op.create_index("ix_fetcher_runs_source_name", "fetcher_runs", ["source_name"])
    op.create_index("ix_fetcher_runs_status", "fetcher_runs", ["status"])
    op.create_index("ix_fetcher_runs_started", "fetcher_runs", ["started_at"])

    # -------------------------------------------------------------- entities
    op.create_table(
        "entities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("canonical_name", sa.String(length=512), nullable=False),
        sa.Column("short_name", sa.String(length=240), nullable=True),
        sa.Column("primary_identifier", sa.String(length=240), nullable=True),
        sa.Column(
            "primary_identifier_scheme", sa.String(length=64), nullable=True
        ),
        sa.Column(
            "instrument_id",
            sa.String(length=36),
            sa.ForeignKey("instruments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "issuer_id",
            sa.String(length=36),
            sa.ForeignKey("issuers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_dataset", sa.String(length=240), nullable=True),
        sa.Column("source_extractor", sa.String(length=120), nullable=True),
        sa.Column(
            "is_canonical",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "parent_id",
            sa.String(length=36),
            sa.ForeignKey("entities.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
    )
    op.create_index("ix_entities_kind", "entities", ["kind"])
    op.create_index("ix_entities_canonical_name", "entities", ["canonical_name"])
    op.create_index("ix_entities_primary_identifier", "entities", ["primary_identifier"])
    op.create_index("ix_entities_instrument_id", "entities", ["instrument_id"])
    op.create_index("ix_entities_issuer_id", "entities", ["issuer_id"])
    op.create_index("ix_entities_kind_name", "entities", ["kind", "canonical_name"])

    op.create_table(
        "entity_identifiers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "entity_id",
            sa.String(length=36),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scheme", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=512), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "entity_id", "scheme", "value", name="uq_entity_identifier_triple"
        ),
    )
    op.create_index(
        "ix_entity_identifiers_entity_id", "entity_identifiers", ["entity_id"]
    )
    op.create_index("ix_entity_identifiers_scheme", "entity_identifiers", ["scheme"])
    op.create_index("ix_entity_identifiers_value", "entity_identifiers", ["value"])

    op.create_table(
        "entity_relations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "subject_id",
            sa.String(length=36),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("predicate", sa.String(length=120), nullable=False),
        sa.Column(
            "object_id",
            sa.String(length=36),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("provenance", sa.String(length=240), nullable=True),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("properties", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_entity_relations_subject", "entity_relations", ["subject_id"])
    op.create_index("ix_entity_relations_object", "entity_relations", ["object_id"])
    op.create_index("ix_entity_relations_predicate", "entity_relations", ["predicate"])
    op.create_index(
        "ix_entity_relations_provenance", "entity_relations", ["provenance"]
    )

    op.create_table(
        "entity_annotations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "entity_id",
            sa.String(length=36),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.String(length=64),
            nullable=False,
            server_default="description",
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("author", sa.String(length=120), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("provider", sa.String(length=120), nullable=True),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
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
    )
    op.create_index(
        "ix_entity_annotations_entity_id", "entity_annotations", ["entity_id"]
    )
    op.create_index("ix_entity_annotations_kind", "entity_annotations", ["kind"])
    op.create_index("ix_entity_annotations_author", "entity_annotations", ["author"])
    op.create_index("ix_entity_annotations_model", "entity_annotations", ["model"])

    op.create_table(
        "entity_dataset_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "entity_id",
            sa.String(length=36),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dataset_catalog_id",
            sa.String(length=36),
            sa.ForeignKey("dataset_catalogs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "dataset_version_id",
            sa.String(length=36),
            sa.ForeignKey("dataset_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("iceberg_identifier", sa.String(length=240), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("coverage_start", sa.DateTime(), nullable=True),
        sa.Column("coverage_end", sa.DateTime(), nullable=True),
        sa.Column("role", sa.String(length=64), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_entity_dataset_links_entity_id", "entity_dataset_links", ["entity_id"]
    )
    op.create_index(
        "ix_entity_dataset_links_dataset",
        "entity_dataset_links",
        ["dataset_catalog_id"],
    )
    op.create_index(
        "ix_entity_dataset_links_iceberg",
        "entity_dataset_links",
        ["iceberg_identifier"],
    )


def downgrade() -> None:
    op.drop_index("ix_entity_dataset_links_iceberg", table_name="entity_dataset_links")
    op.drop_index("ix_entity_dataset_links_dataset", table_name="entity_dataset_links")
    op.drop_index("ix_entity_dataset_links_entity_id", table_name="entity_dataset_links")
    op.drop_table("entity_dataset_links")

    op.drop_index("ix_entity_annotations_model", table_name="entity_annotations")
    op.drop_index("ix_entity_annotations_author", table_name="entity_annotations")
    op.drop_index("ix_entity_annotations_kind", table_name="entity_annotations")
    op.drop_index("ix_entity_annotations_entity_id", table_name="entity_annotations")
    op.drop_table("entity_annotations")

    op.drop_index("ix_entity_relations_provenance", table_name="entity_relations")
    op.drop_index("ix_entity_relations_predicate", table_name="entity_relations")
    op.drop_index("ix_entity_relations_object", table_name="entity_relations")
    op.drop_index("ix_entity_relations_subject", table_name="entity_relations")
    op.drop_table("entity_relations")

    op.drop_index("ix_entity_identifiers_value", table_name="entity_identifiers")
    op.drop_index("ix_entity_identifiers_scheme", table_name="entity_identifiers")
    op.drop_index("ix_entity_identifiers_entity_id", table_name="entity_identifiers")
    op.drop_table("entity_identifiers")

    op.drop_index("ix_entities_kind_name", table_name="entities")
    op.drop_index("ix_entities_issuer_id", table_name="entities")
    op.drop_index("ix_entities_instrument_id", table_name="entities")
    op.drop_index("ix_entities_primary_identifier", table_name="entities")
    op.drop_index("ix_entities_canonical_name", table_name="entities")
    op.drop_index("ix_entities_kind", table_name="entities")
    op.drop_table("entities")

    op.drop_index("ix_fetcher_runs_started", table_name="fetcher_runs")
    op.drop_index("ix_fetcher_runs_status", table_name="fetcher_runs")
    op.drop_index("ix_fetcher_runs_source_name", table_name="fetcher_runs")
    op.drop_table("fetcher_runs")

    op.drop_index("ix_datahub_sync_log_started", table_name="datahub_sync_log")
    op.drop_index("ix_datahub_sync_log_status", table_name="datahub_sync_log")
    op.drop_index("ix_datahub_sync_log_target", table_name="datahub_sync_log")
    op.drop_table("datahub_sync_log")

    op.drop_index("ix_dataset_profiles_lookup", table_name="dataset_profiles")
    op.drop_index("ix_dataset_profiles_name", table_name="dataset_profiles")
    op.drop_index("ix_dataset_profiles_namespace", table_name="dataset_profiles")
    op.drop_table("dataset_profiles")

    op.drop_index("ix_pipeline_runs_started_at", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_status", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_namespace", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_manifest_id", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")

    op.drop_index("ix_pipeline_manifests_enabled", table_name="pipeline_manifests")
    op.drop_index("ix_pipeline_manifests_namespace", table_name="pipeline_manifests")
    op.drop_index("ix_pipeline_manifests_name", table_name="pipeline_manifests")
    op.drop_table("pipeline_manifests")

    op.drop_column("data_sources", "last_probe_at")
    op.drop_column("data_sources", "health_status")
    op.drop_column("data_sources", "endpoints_json")
    op.drop_column("data_sources", "pagination_json")
    op.drop_column("data_sources", "rate_limit_json")
    op.drop_column("data_sources", "transport")
    op.drop_column("data_sources", "kind_subtype")

    op.drop_index("ix_dataset_versions_dagster_run_id", table_name="dataset_versions")
    op.drop_column("dataset_versions", "code_version_sha")
    op.drop_column("dataset_versions", "partition_key")
    op.drop_column("dataset_versions", "dagster_run_id")
    op.drop_column("dataset_versions", "materialization_engine")

    op.drop_index("ix_dataset_catalogs_datahub_urn", table_name="dataset_catalogs")
    op.drop_index(
        "ix_dataset_catalogs_dagster_asset_key", table_name="dataset_catalogs"
    )
    op.drop_column("dataset_catalogs", "pipeline_kind")
    op.drop_column("dataset_catalogs", "manifest_id")
    op.drop_column("dataset_catalogs", "entity_extraction_status")
    op.drop_column("dataset_catalogs", "datahub_urn")
    op.drop_column("dataset_catalogs", "dagster_asset_key")
    op.drop_column("dataset_catalogs", "compute_backend")
