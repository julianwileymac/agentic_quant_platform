"""Management Engine ledger: workload_runs table (AGENTS rule 45).

Revision ID: 0055_workload_runs
Revises: 0054_assistant_engine
Create Date: 2026-05-18

Strictly additive — creates the ``workload_runs`` table that backs
the in-monolith path of the shared
:class:`aqp_platform_core.runtime.WorkloadRuntime`. Every workload
operation (start / stop / scale / restart / exec / logs /
apply_config / rotate_secret / delete) writes one row here BEFORE
dispatching to the active
:class:`aqp_platform_core.providers.InfrastructureProvider`.

The sidecar :mod:`aqp_control_plane` micro-project keeps its JSONL
audit writer (``aqp_cp.services.lifecycle.JsonlAuditSink``); only the
monolith uses this Postgres backing.

AGENTS rule 34 — ``experiment_id`` + ``test_id`` FKs are nullable so
the ``experiments`` / ``tests`` umbrella can stamp ad-hoc operator
ops with the active :class:`aqp.auth.context.RequestContext`. AGENTS
rule 6 — this migration is immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0055_workload_runs"
down_revision = "0054_assistant_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workload_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_uid",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("provider_alias", sa.String(length=80), nullable=False),
        sa.Column("target", sa.String(length=240), nullable=False),
        sa.Column("namespace", sa.String(length=120), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("experiment_id", sa.String(length=36), nullable=True),
        sa.Column("test_id", sa.String(length=36), nullable=True),
        sa.Column("request_id", sa.String(length=120), nullable=True),
        sa.Column(
            "payload",
            sa.JSON().with_variant(
                sa.dialects.postgresql.JSONB(), "postgresql"
            ),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "result",
            sa.JSON().with_variant(
                sa.dialects.postgresql.JSONB(), "postgresql"
            ),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("halt_reason", sa.String(length=120), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["aqp_experiments.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["test_id"], ["aqp_tests.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("run_uid", name="uq_workload_runs_run_uid"),
    )
    op.create_index(
        "ix_workload_runs_run_uid",
        "workload_runs",
        ["run_uid"],
    )
    op.create_index(
        "ix_workload_runs_started_at",
        "workload_runs",
        ["started_at"],
    )
    op.create_index(
        "ix_workload_runs_status",
        "workload_runs",
        ["status"],
    )
    op.create_index(
        "ix_workload_runs_action",
        "workload_runs",
        ["action"],
    )
    op.create_index(
        "ix_workload_runs_provider_alias",
        "workload_runs",
        ["provider_alias"],
    )
    op.create_index(
        "ix_workload_runs_target",
        "workload_runs",
        ["target"],
    )
    op.create_index(
        "ix_workload_runs_namespace",
        "workload_runs",
        ["namespace"],
    )
    op.create_index(
        "ix_workload_runs_user_id",
        "workload_runs",
        ["user_id"],
    )
    op.create_index(
        "ix_workload_runs_organization_id",
        "workload_runs",
        ["organization_id"],
    )
    op.create_index(
        "ix_workload_runs_workspace_id",
        "workload_runs",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workload_runs_experiment_id",
        "workload_runs",
        ["experiment_id"],
    )
    op.create_index(
        "ix_workload_runs_test_id",
        "workload_runs",
        ["test_id"],
    )
    op.create_index(
        "ix_workload_runs_request_id",
        "workload_runs",
        ["request_id"],
    )
    op.create_index(
        "ix_workload_runs_status_started_desc",
        "workload_runs",
        ["status", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_workload_runs_action_started_desc",
        "workload_runs",
        ["action", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_workload_runs_provider_target",
        "workload_runs",
        ["provider_alias", "target"],
    )


def downgrade() -> None:
    for index_name in (
        "ix_workload_runs_provider_target",
        "ix_workload_runs_action_started_desc",
        "ix_workload_runs_status_started_desc",
        "ix_workload_runs_request_id",
        "ix_workload_runs_test_id",
        "ix_workload_runs_experiment_id",
        "ix_workload_runs_workspace_id",
        "ix_workload_runs_organization_id",
        "ix_workload_runs_user_id",
        "ix_workload_runs_namespace",
        "ix_workload_runs_target",
        "ix_workload_runs_provider_alias",
        "ix_workload_runs_action",
        "ix_workload_runs_status",
        "ix_workload_runs_started_at",
        "ix_workload_runs_run_uid",
    ):
        try:
            op.drop_index(index_name, table_name="workload_runs")
        except Exception:  # noqa: BLE001
            pass
    op.drop_table("workload_runs")
