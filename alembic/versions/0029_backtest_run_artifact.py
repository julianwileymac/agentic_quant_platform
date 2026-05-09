"""Add backtest_run_artifacts for off-row storage of equity curves / trade logs.

Revision ID: 0029_backtest_run_artifact
Revises: 0028_tenancy_pipeline_manifest_uniqueness
Create Date: 2026-05-09

The :class:`BacktestRun` row stores summary stats + a compact
``metrics`` JSON blob. Full equity curves, trade logs, signal logs
and event-log replays are too large for the relational row, so they
go into MinIO/S3 and this table holds the pointers + per-artifact
summary stats. Phase 4's iterative optimisation loop reads the
``confidence_intervals`` artifact to decide whether the previous run
beat the user-supplied threshold.

Inherits the :class:`ProjectScopedMixin` columns
(``owner_user_id`` / ``workspace_id`` / ``project_id``) so artifacts
remain workspace-isolated.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0029_backtest_run_artifact"
down_revision = "0028_tenancy_manifest_uq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backtest_run_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("backtest_run_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_kind", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.String(length=1024), nullable=False),
        sa.Column("bytes_size", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        # ProjectScopedMixin columns
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["backtest_run_id"], ["backtest_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_backtest_run_artifacts_run_kind",
        "backtest_run_artifacts",
        ["backtest_run_id", "artifact_kind"],
    )
    op.create_index(
        "ix_backtest_run_artifacts_workspace_id",
        "backtest_run_artifacts",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_backtest_run_artifacts_workspace_id", table_name="backtest_run_artifacts"
    )
    op.drop_index(
        "ix_backtest_run_artifacts_run_kind", table_name="backtest_run_artifacts"
    )
    op.drop_table("backtest_run_artifacts")
