"""Phase 5: pricing-context audit run rows + ML predictor spec versions.

Revision ID: 0044_pricing_context_runs
Revises: 0043_reconciliation_anomalies
Create Date: 2026-05-16

Adds two tables:

* ``pricing_context_runs`` -- one row per :class:`PricingContext`
  execution. Captures the active context state (as_of, dispatch mode,
  behaviour), the measure that was computed, the elapsed time, and
  the resulting value (small) or arrow_identifier (large). The Phase 5
  ``data.pricing.*`` MCP tools read this table for explanation /
  audit. Carries ``experiment_id`` (AGENTS rule 34).

* ``predictor_spec_versions`` -- one row per hash-locked
  :class:`PredictorSpec` snapshot. Mirrors the spec-version pattern
  used by AgentSpec / BotSpec / RLExperimentSpec / AnalysisSpec
  (AGENTS rules 13 / 15 / 17 / 24). The hash changes -> a new row,
  never mutate.

AGENTS rule 6: this migration is **immutable** once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0044_pricing_context_runs"
down_revision = "0043_reconciliation_anomalies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --------------------------------------------------------------
    # pricing_context_runs
    # --------------------------------------------------------------
    op.create_table(
        "pricing_context_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("context_id", sa.String(length=64), nullable=False),
        # User-friendly id (e.g. UUID-ish); allows multi-step "what
        # measures did we run inside this context" lookups.
        sa.Column("measure", sa.String(length=64), nullable=False),
        sa.Column("instrument_class", sa.String(length=120), nullable=True),
        sa.Column("instrument_ref", sa.String(length=240), nullable=True),
        # Free-form text describing the instrument (vt_symbol, portfolio id, etc.)
        sa.Column("as_of", sa.DateTime(), nullable=True),
        sa.Column("market_data_source", sa.String(length=120), nullable=True),
        sa.Column("behaviour", sa.String(length=32), nullable=True),
        sa.Column("dispatch", sa.String(length=16), nullable=False),
        # sync | async | celery
        sa.Column("status", sa.String(length=24), nullable=False, server_default="running"),
        # running | completed | error
        sa.Column("value_scalar", sa.Float(), nullable=True),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("arrow_identifier", sa.String(length=240), nullable=True),
        # When the result is too big to inline -- Iceberg identifier
        sa.Column("elapsed_ms", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("experiment_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("ts_started", sa.DateTime(), nullable=False),
        sa.Column("ts_completed", sa.DateTime(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["aqp_experiments.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pricing_context_runs_context_id", "pricing_context_runs", ["context_id"])
    op.create_index("ix_pricing_context_runs_measure", "pricing_context_runs", ["measure"])
    op.create_index(
        "ix_pricing_context_runs_instrument_class",
        "pricing_context_runs",
        ["instrument_class"],
    )
    op.create_index(
        "ix_pricing_context_runs_status", "pricing_context_runs", ["status"]
    )
    op.create_index(
        "ix_pricing_context_runs_ts_started", "pricing_context_runs", ["ts_started"]
    )
    op.create_index(
        "ix_pricing_context_runs_workspace_id",
        "pricing_context_runs",
        ["workspace_id"],
    )
    op.create_index(
        "ix_pricing_context_runs_experiment_id",
        "pricing_context_runs",
        ["experiment_id"],
    )

    # --------------------------------------------------------------
    # predictor_spec_versions
    # --------------------------------------------------------------
    op.create_table(
        "predictor_spec_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("predictor_name", sa.String(length=120), nullable=False),
        sa.Column("spec_hash", sa.String(length=64), nullable=False),
        # SHA-256 of the canonical-JSON spec body
        sa.Column("spec_body", sa.JSON(), nullable=False),
        sa.Column("model_kind", sa.String(length=32), nullable=False),
        # xgboost | lstm | transformer | linear | tcn | ...
        sa.Column("target_horizon", sa.String(length=32), nullable=False),
        # 1d | 5d | 30d | event | adhoc
        sa.Column("label_kind", sa.String(length=24), nullable=False),
        # regression | classification | ranking
        sa.Column("feature_columns", sa.JSON(), nullable=True),
        sa.Column("hyperparams_json", sa.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "predictor_name",
            "spec_hash",
            name="uq_predictor_spec_versions_name_hash",
        ),
    )
    op.create_index("ix_predictor_spec_versions_name", "predictor_spec_versions", ["predictor_name"])
    op.create_index(
        "ix_predictor_spec_versions_model_kind",
        "predictor_spec_versions",
        ["model_kind"],
    )
    op.create_index(
        "ix_predictor_spec_versions_target_horizon",
        "predictor_spec_versions",
        ["target_horizon"],
    )
    op.create_index(
        "ix_predictor_spec_versions_label_kind",
        "predictor_spec_versions",
        ["label_kind"],
    )
    op.create_index(
        "ix_predictor_spec_versions_workspace_id",
        "predictor_spec_versions",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_predictor_spec_versions_workspace_id",
        table_name="predictor_spec_versions",
    )
    op.drop_index(
        "ix_predictor_spec_versions_label_kind",
        table_name="predictor_spec_versions",
    )
    op.drop_index(
        "ix_predictor_spec_versions_target_horizon",
        table_name="predictor_spec_versions",
    )
    op.drop_index(
        "ix_predictor_spec_versions_model_kind",
        table_name="predictor_spec_versions",
    )
    op.drop_index(
        "ix_predictor_spec_versions_name", table_name="predictor_spec_versions"
    )
    op.drop_table("predictor_spec_versions")

    op.drop_index(
        "ix_pricing_context_runs_experiment_id",
        table_name="pricing_context_runs",
    )
    op.drop_index(
        "ix_pricing_context_runs_workspace_id",
        table_name="pricing_context_runs",
    )
    op.drop_index(
        "ix_pricing_context_runs_ts_started",
        table_name="pricing_context_runs",
    )
    op.drop_index(
        "ix_pricing_context_runs_status", table_name="pricing_context_runs"
    )
    op.drop_index(
        "ix_pricing_context_runs_instrument_class",
        table_name="pricing_context_runs",
    )
    op.drop_index(
        "ix_pricing_context_runs_measure", table_name="pricing_context_runs"
    )
    op.drop_index(
        "ix_pricing_context_runs_context_id", table_name="pricing_context_runs"
    )
    op.drop_table("pricing_context_runs")
