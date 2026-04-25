"""add quant ml planning + deployment lineage tables

Revision ID: 0004_quant_ml_planning
Revises: 0003_optimizer_and_crew
Create Date: 2026-04-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_quant_ml_planning"
down_revision = "0003_optimizer_and_crew"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("model_versions", sa.Column("dataset_version_id", sa.String(length=36), nullable=True))
    op.add_column("model_versions", sa.Column("split_plan_id", sa.String(length=36), nullable=True))
    op.add_column("model_versions", sa.Column("pipeline_recipe_id", sa.String(length=36), nullable=True))
    op.add_column("model_versions", sa.Column("experiment_plan_id", sa.String(length=36), nullable=True))

    op.create_table(
        "instruments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("vt_symbol", sa.String(length=64), nullable=False),
        sa.Column("ticker", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=True),
        sa.Column("asset_class", sa.String(length=32), nullable=True),
        sa.Column("security_type", sa.String(length=32), nullable=True),
        sa.Column("identifiers", sa.JSON(), nullable=True),
        sa.Column("sector", sa.String(length=120), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("region", sa.String(length=64), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_instruments_vt_symbol", "instruments", ["vt_symbol"], unique=True)
    op.create_index("ix_instruments_ticker", "instruments", ["ticker"], unique=False)

    op.create_table(
        "dataset_catalogs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("domain", sa.String(length=120), nullable=False, server_default="market.bars"),
        sa.Column("frequency", sa.String(length=32), nullable=True),
        sa.Column("storage_uri", sa.String(length=512), nullable=True),
        sa.Column("schema_json", sa.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_dataset_catalogs_name", "dataset_catalogs", ["name"], unique=False)
    op.create_index(
        "ix_dataset_catalogs_provider",
        "dataset_catalogs",
        ["provider"],
        unique=False,
    )
    op.create_index(
        "ix_dataset_catalog_name_provider",
        "dataset_catalogs",
        ["name", "provider"],
        unique=False,
    )

    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("catalog_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("as_of", sa.DateTime(), nullable=True),
        sa.Column("start_time", sa.DateTime(), nullable=True),
        sa.Column("end_time", sa.DateTime(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("symbol_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dataset_hash", sa.String(length=64), nullable=True),
        sa.Column("materialization_uri", sa.String(length=512), nullable=True),
        sa.Column("columns", sa.JSON(), nullable=True),
        sa.Column("schema_json", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["catalog_id"], ["dataset_catalogs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_dataset_versions_catalog_id", "dataset_versions", ["catalog_id"], unique=False)
    op.create_index(
        "ix_dataset_versions_catalog_version",
        "dataset_versions",
        ["catalog_id", "version"],
        unique=False,
    )
    op.create_index("ix_dataset_versions_status", "dataset_versions", ["status"], unique=False)
    op.create_index("ix_dataset_versions_as_of", "dataset_versions", ["as_of"], unique=False)
    op.create_index(
        "ix_dataset_versions_dataset_hash",
        "dataset_versions",
        ["dataset_hash"],
        unique=False,
    )

    op.create_table(
        "pipeline_recipes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("shared_processors", sa.JSON(), nullable=True),
        sa.Column("infer_processors", sa.JSON(), nullable=True),
        sa.Column("learn_processors", sa.JSON(), nullable=True),
        sa.Column("fit_window", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_pipeline_recipes_name", "pipeline_recipes", ["name"], unique=False)
    op.create_index(
        "ix_pipeline_recipes_name_version",
        "pipeline_recipes",
        ["name", "version"],
        unique=False,
    )

    op.create_table(
        "split_plans",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("method", sa.String(length=40), nullable=False, server_default="fixed"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("dataset_version_id", sa.String(length=36), nullable=True),
        sa.Column("dataset_hash", sa.String(length=64), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("segments", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"]),
    )
    op.create_index("ix_split_plans_name", "split_plans", ["name"], unique=False)
    op.create_index(
        "ix_split_plans_dataset_version_id",
        "split_plans",
        ["dataset_version_id"],
        unique=False,
    )
    op.create_index("ix_split_plans_dataset_hash", "split_plans", ["dataset_hash"], unique=False)

    op.create_table(
        "split_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("split_plan_id", sa.String(length=36), nullable=False),
        sa.Column("fold_name", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("segment", sa.String(length=32), nullable=False, server_default="train"),
        sa.Column("start_time", sa.DateTime(), nullable=True),
        sa.Column("end_time", sa.DateTime(), nullable=True),
        sa.Column("indices", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["split_plan_id"],
            ["split_plans.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_split_artifacts_split_plan_id",
        "split_artifacts",
        ["split_plan_id"],
        unique=False,
    )
    op.create_index(
        "ix_split_artifacts_plan_fold_segment",
        "split_artifacts",
        ["split_plan_id", "fold_name", "segment"],
        unique=False,
    )

    op.create_table(
        "experiment_plans",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("dataset_version_id", sa.String(length=36), nullable=True),
        sa.Column("split_plan_id", sa.String(length=36), nullable=True),
        sa.Column("pipeline_recipe_id", sa.String(length=36), nullable=True),
        sa.Column("dataset_cfg", sa.JSON(), nullable=True),
        sa.Column("model_cfg", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_run_id", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"]),
        sa.ForeignKeyConstraint(["split_plan_id"], ["split_plans.id"]),
        sa.ForeignKeyConstraint(["pipeline_recipe_id"], ["pipeline_recipes.id"]),
    )
    op.create_index("ix_experiment_plans_name", "experiment_plans", ["name"], unique=False)
    op.create_index("ix_experiment_plans_status", "experiment_plans", ["status"], unique=False)
    op.create_index(
        "ix_experiment_plans_dataset_version_id",
        "experiment_plans",
        ["dataset_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_experiment_plans_split_plan_id",
        "experiment_plans",
        ["split_plan_id"],
        unique=False,
    )
    op.create_index(
        "ix_experiment_plans_pipeline_recipe_id",
        "experiment_plans",
        ["pipeline_recipe_id"],
        unique=False,
    )

    op.create_table(
        "model_deployments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="staging"),
        sa.Column("model_version_id", sa.String(length=36), nullable=False),
        sa.Column("experiment_plan_id", sa.String(length=36), nullable=True),
        sa.Column("dataset_version_id", sa.String(length=36), nullable=True),
        sa.Column("split_plan_id", sa.String(length=36), nullable=True),
        sa.Column("pipeline_recipe_id", sa.String(length=36), nullable=True),
        sa.Column("alpha_class", sa.String(length=64), nullable=False, server_default="DeployedModelAlpha"),
        sa.Column("infer_segment", sa.String(length=32), nullable=False, server_default="infer"),
        sa.Column("long_threshold", sa.Float(), nullable=False, server_default="0.001"),
        sa.Column("short_threshold", sa.Float(), nullable=False, server_default="-0.001"),
        sa.Column("allow_short", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("top_k", sa.Integer(), nullable=True),
        sa.Column("deployment_config", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"]),
        sa.ForeignKeyConstraint(["experiment_plan_id"], ["experiment_plans.id"]),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"]),
        sa.ForeignKeyConstraint(["split_plan_id"], ["split_plans.id"]),
        sa.ForeignKeyConstraint(["pipeline_recipe_id"], ["pipeline_recipes.id"]),
    )
    op.create_index("ix_model_deployments_name", "model_deployments", ["name"], unique=False)
    op.create_index("ix_model_deployments_status", "model_deployments", ["status"], unique=False)
    op.create_index(
        "ix_model_deployments_model_version_id",
        "model_deployments",
        ["model_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_model_deployments_experiment_plan_id",
        "model_deployments",
        ["experiment_plan_id"],
        unique=False,
    )
    op.create_index(
        "ix_model_deployments_dataset_version_id",
        "model_deployments",
        ["dataset_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_model_deployments_split_plan_id",
        "model_deployments",
        ["split_plan_id"],
        unique=False,
    )
    op.create_index(
        "ix_model_deployments_pipeline_recipe_id",
        "model_deployments",
        ["pipeline_recipe_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_model_versions_dataset_version_id",
        "model_versions",
        "dataset_versions",
        ["dataset_version_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_model_versions_split_plan_id",
        "model_versions",
        "split_plans",
        ["split_plan_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_model_versions_pipeline_recipe_id",
        "model_versions",
        "pipeline_recipes",
        ["pipeline_recipe_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_model_versions_experiment_plan_id",
        "model_versions",
        "experiment_plans",
        ["experiment_plan_id"],
        ["id"],
    )
    op.create_index("ix_model_versions_dataset_version_id", "model_versions", ["dataset_version_id"], unique=False)
    op.create_index("ix_model_versions_split_plan_id", "model_versions", ["split_plan_id"], unique=False)
    op.create_index(
        "ix_model_versions_pipeline_recipe_id",
        "model_versions",
        ["pipeline_recipe_id"],
        unique=False,
    )
    op.create_index(
        "ix_model_versions_experiment_plan_id",
        "model_versions",
        ["experiment_plan_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_model_versions_experiment_plan_id", table_name="model_versions")
    op.drop_index("ix_model_versions_pipeline_recipe_id", table_name="model_versions")
    op.drop_index("ix_model_versions_split_plan_id", table_name="model_versions")
    op.drop_index("ix_model_versions_dataset_version_id", table_name="model_versions")
    op.drop_constraint("fk_model_versions_experiment_plan_id", "model_versions", type_="foreignkey")
    op.drop_constraint("fk_model_versions_pipeline_recipe_id", "model_versions", type_="foreignkey")
    op.drop_constraint("fk_model_versions_split_plan_id", "model_versions", type_="foreignkey")
    op.drop_constraint("fk_model_versions_dataset_version_id", "model_versions", type_="foreignkey")
    op.drop_column("model_versions", "experiment_plan_id")
    op.drop_column("model_versions", "pipeline_recipe_id")
    op.drop_column("model_versions", "split_plan_id")
    op.drop_column("model_versions", "dataset_version_id")

    op.drop_index("ix_model_deployments_pipeline_recipe_id", table_name="model_deployments")
    op.drop_index("ix_model_deployments_split_plan_id", table_name="model_deployments")
    op.drop_index("ix_model_deployments_dataset_version_id", table_name="model_deployments")
    op.drop_index("ix_model_deployments_experiment_plan_id", table_name="model_deployments")
    op.drop_index("ix_model_deployments_model_version_id", table_name="model_deployments")
    op.drop_index("ix_model_deployments_status", table_name="model_deployments")
    op.drop_index("ix_model_deployments_name", table_name="model_deployments")
    op.drop_table("model_deployments")

    op.drop_index("ix_experiment_plans_pipeline_recipe_id", table_name="experiment_plans")
    op.drop_index("ix_experiment_plans_split_plan_id", table_name="experiment_plans")
    op.drop_index("ix_experiment_plans_dataset_version_id", table_name="experiment_plans")
    op.drop_index("ix_experiment_plans_status", table_name="experiment_plans")
    op.drop_index("ix_experiment_plans_name", table_name="experiment_plans")
    op.drop_table("experiment_plans")

    op.drop_index("ix_split_artifacts_plan_fold_segment", table_name="split_artifacts")
    op.drop_index("ix_split_artifacts_split_plan_id", table_name="split_artifacts")
    op.drop_table("split_artifacts")

    op.drop_index("ix_split_plans_dataset_hash", table_name="split_plans")
    op.drop_index("ix_split_plans_dataset_version_id", table_name="split_plans")
    op.drop_index("ix_split_plans_name", table_name="split_plans")
    op.drop_table("split_plans")

    op.drop_index("ix_pipeline_recipes_name_version", table_name="pipeline_recipes")
    op.drop_index("ix_pipeline_recipes_name", table_name="pipeline_recipes")
    op.drop_table("pipeline_recipes")

    op.drop_index("ix_dataset_versions_dataset_hash", table_name="dataset_versions")
    op.drop_index("ix_dataset_versions_as_of", table_name="dataset_versions")
    op.drop_index("ix_dataset_versions_status", table_name="dataset_versions")
    op.drop_index("ix_dataset_versions_catalog_version", table_name="dataset_versions")
    op.drop_index("ix_dataset_versions_catalog_id", table_name="dataset_versions")
    op.drop_table("dataset_versions")

    op.drop_index("ix_dataset_catalog_name_provider", table_name="dataset_catalogs")
    op.drop_index("ix_dataset_catalogs_provider", table_name="dataset_catalogs")
    op.drop_index("ix_dataset_catalogs_name", table_name="dataset_catalogs")
    op.drop_table("dataset_catalogs")

    op.drop_index("ix_instruments_ticker", table_name="instruments")
    op.drop_index("ix_instruments_vt_symbol", table_name="instruments")
    op.drop_table("instruments")
