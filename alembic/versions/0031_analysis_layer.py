"""Analysis layer — hash-locked AnalysisSpec + run / step-result ledger.

Revision ID: 0031_analysis_layer
Revises: 0030_strategy_regime_memory
Create Date: 2026-05-09

Adds the four tables that back :mod:`aqp.analysis`:

- ``analysis_specs`` — logical row keyed on ``(project_id, slug)``.
- ``analysis_spec_versions`` — immutable, hash-locked snapshot of
  every :class:`AnalysisSpec` the registry has ever seen.
- ``analysis_runs`` — one row per ``run`` / ``preview`` invocation
  of :class:`aqp.analysis.runtime.AnalysisRuntime`.
- ``analysis_step_results`` — one row per :class:`AnalysisStep` in
  the spec, joined to ``analysis_runs`` via ``run_id``.

Mirrors the ``0026_rl_layer`` migration shape so schema reviews are
easy. The four tables are project-scoped via ``ProjectScopedMixin``;
gold-tier Iceberg outputs land under ``aqp_gold_analysis_*``
namespaces validated by :func:`aqp.data.iceberg_catalog.append_arrow`.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0031_analysis_layer"
down_revision = "0030_strategy_regime_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --------------------------------------------------- analysis_specs
    op.create_table(
        "analysis_specs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="research"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("spec_yaml", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("annotations", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        # ProjectScopedMixin
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "slug", name="uq_analysis_specs_project_slug"
        ),
    )
    op.create_index("ix_analysis_specs_slug", "analysis_specs", ["slug"])
    op.create_index("ix_analysis_specs_kind", "analysis_specs", ["kind"])
    op.create_index("ix_analysis_specs_status", "analysis_specs", ["status"])
    op.create_index(
        "ix_analysis_specs_workspace_id", "analysis_specs", ["workspace_id"]
    )
    op.create_index(
        "ix_analysis_specs_project_id", "analysis_specs", ["project_id"]
    )
    op.create_index(
        "ix_analysis_specs_owner_user_id", "analysis_specs", ["owner_user_id"]
    )

    # ----------------------------------------- analysis_spec_versions
    op.create_table(
        "analysis_spec_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("spec_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("spec_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["spec_id"], ["analysis_specs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "spec_id", "spec_hash", name="uq_analysis_versions_spec_hash"
        ),
        sa.UniqueConstraint(
            "spec_id", "version", name="uq_analysis_versions_spec_version"
        ),
    )
    op.create_index(
        "ix_analysis_versions_spec_id", "analysis_spec_versions", ["spec_id"]
    )
    op.create_index(
        "ix_analysis_versions_spec_hash",
        "analysis_spec_versions",
        ["spec_hash"],
    )
    op.create_index(
        "ix_analysis_versions_spec_version",
        "analysis_spec_versions",
        ["spec_id", "version"],
    )
    op.create_index(
        "ix_analysis_versions_workspace_id",
        "analysis_spec_versions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_analysis_versions_project_id",
        "analysis_spec_versions",
        ["project_id"],
    )

    # --------------------------------------------------- analysis_runs
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("spec_id", sa.String(length=36), nullable=True),
        sa.Column("version_id", sa.String(length=36), nullable=True),
        sa.Column("target", sa.String(length=40), nullable=False, server_default="run"),
        sa.Column("task_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("dataset_descriptor", sa.String(length=400), nullable=True),
        sa.Column("dataset_hash", sa.String(length=64), nullable=True),
        sa.Column("mlflow_run_id", sa.String(length=120), nullable=True),
        sa.Column("iceberg_result_table", sa.String(length=240), nullable=True),
        sa.Column("result_summary", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["spec_id"], ["analysis_specs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["analysis_spec_versions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_runs_spec_id", "analysis_runs", ["spec_id"])
    op.create_index(
        "ix_analysis_runs_version_id", "analysis_runs", ["version_id"]
    )
    op.create_index("ix_analysis_runs_target", "analysis_runs", ["target"])
    op.create_index("ix_analysis_runs_task_id", "analysis_runs", ["task_id"])
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"])
    op.create_index(
        "ix_analysis_runs_status_started",
        "analysis_runs",
        ["status", "started_at"],
    )
    op.create_index(
        "ix_analysis_runs_workspace_id", "analysis_runs", ["workspace_id"]
    )
    op.create_index(
        "ix_analysis_runs_project_id", "analysis_runs", ["project_id"]
    )

    # ------------------------------------------- analysis_step_results
    op.create_table(
        "analysis_step_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("step_alias", sa.String(length=160), nullable=False),
        sa.Column("flow", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("params_json", sa.JSON(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("artifact_uri", sa.String(length=400), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["analysis_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "step_alias", name="uq_analysis_step_results_run_alias"
        ),
    )
    op.create_index(
        "ix_analysis_step_results_run_id",
        "analysis_step_results",
        ["run_id"],
    )
    op.create_index(
        "ix_analysis_step_results_step_alias",
        "analysis_step_results",
        ["step_alias"],
    )
    op.create_index(
        "ix_analysis_step_results_flow",
        "analysis_step_results",
        ["flow"],
    )
    op.create_index(
        "ix_analysis_step_results_status",
        "analysis_step_results",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analysis_step_results_status", table_name="analysis_step_results"
    )
    op.drop_index(
        "ix_analysis_step_results_flow", table_name="analysis_step_results"
    )
    op.drop_index(
        "ix_analysis_step_results_step_alias",
        table_name="analysis_step_results",
    )
    op.drop_index(
        "ix_analysis_step_results_run_id", table_name="analysis_step_results"
    )
    op.drop_table("analysis_step_results")

    op.drop_index("ix_analysis_runs_project_id", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_workspace_id", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_status_started", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_status", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_task_id", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_target", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_version_id", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_spec_id", table_name="analysis_runs")
    op.drop_table("analysis_runs")

    op.drop_index(
        "ix_analysis_versions_project_id",
        table_name="analysis_spec_versions",
    )
    op.drop_index(
        "ix_analysis_versions_workspace_id",
        table_name="analysis_spec_versions",
    )
    op.drop_index(
        "ix_analysis_versions_spec_version",
        table_name="analysis_spec_versions",
    )
    op.drop_index(
        "ix_analysis_versions_spec_hash",
        table_name="analysis_spec_versions",
    )
    op.drop_index(
        "ix_analysis_versions_spec_id",
        table_name="analysis_spec_versions",
    )
    op.drop_table("analysis_spec_versions")

    op.drop_index(
        "ix_analysis_specs_owner_user_id", table_name="analysis_specs"
    )
    op.drop_index(
        "ix_analysis_specs_project_id", table_name="analysis_specs"
    )
    op.drop_index(
        "ix_analysis_specs_workspace_id", table_name="analysis_specs"
    )
    op.drop_index("ix_analysis_specs_status", table_name="analysis_specs")
    op.drop_index("ix_analysis_specs_kind", table_name="analysis_specs")
    op.drop_index("ix_analysis_specs_slug", table_name="analysis_specs")
    op.drop_table("analysis_specs")
