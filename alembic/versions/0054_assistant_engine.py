"""Assistant Engine ledger + spec versioning + session/message/event tables.

Revision ID: 0054_assistant_engine
Revises: 0053_paper_metadata_seed_aspects
Create Date: 2026-05-18

Strictly additive — creates seven new tables for the Assistant Engine
control plane (Phase 2 of the assistant-engine-for-aqp plan):

- ``assistant_specs`` — logical assistant + ``current_version`` cursor.
- ``assistant_spec_versions`` — immutable, hash-locked snapshot rows.
- ``assistant_sessions`` — per-user conversation thread.
- ``assistant_messages`` — user / assistant / tool message turns.
- ``assistant_runs`` — one execution by :class:`AssistantRuntime`,
  links to ``agent_runs_v2.id`` or ``workflow_runs.id`` via
  ``target_run_kind`` + ``target_run_id``, carries the
  ``experiment_id`` / ``test_id`` FKs (rule 34).
- ``assistant_run_events`` — structured timeline events.
- ``assistant_skills`` — Markdown skill descriptor cache.

The migration never edits the rows on any prior table. ORM definitions
live in :mod:`aqp.persistence.models_assistants`.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0054_assistant_engine"
down_revision = "0053_paper_metadata_seed_aspects"
branch_labels = None
depends_on = None


def _project_scoped_columns() -> list[sa.Column]:
    """Match :class:`aqp.persistence._tenancy_mixins.ProjectScopedMixin`."""
    return [
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "assistant_specs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="agent"),
        sa.Column("target_ref", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("annotations", sa.JSON(), nullable=True),
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
        *_project_scoped_columns(),
        sa.UniqueConstraint("name", name="uq_assistant_specs_name"),
    )
    op.create_index(
        "ix_assistant_specs_name", "assistant_specs", ["name"], unique=False
    )
    op.create_index(
        "ix_assistant_specs_owner_user_id",
        "assistant_specs",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_assistant_specs_workspace_id",
        "assistant_specs",
        ["workspace_id"],
    )
    op.create_index(
        "ix_assistant_specs_project_id",
        "assistant_specs",
        ["project_id"],
    )

    op.create_table(
        "assistant_spec_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "spec_id",
            sa.String(length=36),
            sa.ForeignKey("assistant_specs.id", ondelete="CASCADE"),
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
        *_project_scoped_columns(),
        sa.UniqueConstraint("spec_hash", name="uq_assistant_spec_versions_hash"),
    )
    op.create_index(
        "ix_assistant_spec_versions_spec_id",
        "assistant_spec_versions",
        ["spec_id"],
    )
    op.create_index(
        "ix_assistant_spec_versions_spec_version",
        "assistant_spec_versions",
        ["spec_id", "version"],
    )

    op.create_table(
        "assistant_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("assistant_spec_name", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_active_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        *_project_scoped_columns(),
    )
    op.create_index(
        "ix_assistant_sessions_assistant_spec_name",
        "assistant_sessions",
        ["assistant_spec_name"],
    )
    op.create_index(
        "ix_assistant_sessions_active",
        "assistant_sessions",
        ["assistant_spec_name", "last_active_at"],
    )

    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("assistant_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        *_project_scoped_columns(),
    )
    op.create_index(
        "ix_assistant_messages_session_id",
        "assistant_messages",
        ["session_id"],
    )
    op.create_index(
        "ix_assistant_messages_run_id",
        "assistant_messages",
        ["run_id"],
    )
    op.create_index(
        "ix_assistant_messages_session_turn",
        "assistant_messages",
        ["session_id", "turn"],
    )

    op.create_table(
        "assistant_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("assistant_spec_name", sa.String(length=160), nullable=False),
        sa.Column(
            "spec_version_id",
            sa.String(length=36),
            sa.ForeignKey("assistant_spec_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("assistant_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("task_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("target_kind", sa.String(length=16), nullable=False, server_default="agent"),
        sa.Column("target_ref", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("target_run_kind", sa.String(length=16), nullable=True),
        sa.Column("target_run_id", sa.String(length=36), nullable=True),
        sa.Column("inputs", sa.JSON(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("n_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_tool_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_rag_hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("halted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("halt_token", sa.String(length=64), nullable=True),
        sa.Column("halted_at", sa.DateTime(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column(
            "experiment_id",
            sa.String(length=36),
            sa.ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "test_id",
            sa.String(length=36),
            sa.ForeignKey("aqp_tests.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *_project_scoped_columns(),
    )
    op.create_index(
        "ix_assistant_runs_assistant_spec_name",
        "assistant_runs",
        ["assistant_spec_name"],
    )
    op.create_index(
        "ix_assistant_runs_status",
        "assistant_runs",
        ["status"],
    )
    op.create_index(
        "ix_assistant_runs_status_started",
        "assistant_runs",
        ["status", "started_at"],
    )
    op.create_index(
        "ix_assistant_runs_session_id",
        "assistant_runs",
        ["session_id"],
    )
    op.create_index(
        "ix_assistant_runs_task_id",
        "assistant_runs",
        ["task_id"],
    )
    op.create_index(
        "ix_assistant_runs_target_run_id",
        "assistant_runs",
        ["target_run_id"],
    )
    op.create_index(
        "ix_assistant_runs_experiment_id",
        "assistant_runs",
        ["experiment_id"],
    )
    op.create_index(
        "ix_assistant_runs_test_id",
        "assistant_runs",
        ["test_id"],
    )

    op.create_table(
        "assistant_run_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("assistant_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        *_project_scoped_columns(),
    )
    op.create_index(
        "ix_assistant_run_events_run_id",
        "assistant_run_events",
        ["run_id"],
    )
    op.create_index(
        "ix_assistant_run_events_run_seq",
        "assistant_run_events",
        ["run_id", "seq"],
    )

    op.create_table(
        "assistant_skills",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
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
        *_project_scoped_columns(),
        sa.UniqueConstraint("slug", name="uq_assistant_skills_slug"),
    )
    op.create_index(
        "ix_assistant_skills_slug", "assistant_skills", ["slug"]
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_skills_slug", table_name="assistant_skills")
    op.drop_table("assistant_skills")

    op.drop_index(
        "ix_assistant_run_events_run_seq", table_name="assistant_run_events"
    )
    op.drop_index(
        "ix_assistant_run_events_run_id", table_name="assistant_run_events"
    )
    op.drop_table("assistant_run_events")

    op.drop_index("ix_assistant_runs_test_id", table_name="assistant_runs")
    op.drop_index("ix_assistant_runs_experiment_id", table_name="assistant_runs")
    op.drop_index("ix_assistant_runs_target_run_id", table_name="assistant_runs")
    op.drop_index("ix_assistant_runs_task_id", table_name="assistant_runs")
    op.drop_index("ix_assistant_runs_session_id", table_name="assistant_runs")
    op.drop_index("ix_assistant_runs_status_started", table_name="assistant_runs")
    op.drop_index("ix_assistant_runs_status", table_name="assistant_runs")
    op.drop_index(
        "ix_assistant_runs_assistant_spec_name", table_name="assistant_runs"
    )
    op.drop_table("assistant_runs")

    op.drop_index(
        "ix_assistant_messages_session_turn", table_name="assistant_messages"
    )
    op.drop_index(
        "ix_assistant_messages_run_id", table_name="assistant_messages"
    )
    op.drop_index(
        "ix_assistant_messages_session_id", table_name="assistant_messages"
    )
    op.drop_table("assistant_messages")

    op.drop_index("ix_assistant_sessions_active", table_name="assistant_sessions")
    op.drop_index(
        "ix_assistant_sessions_assistant_spec_name",
        table_name="assistant_sessions",
    )
    op.drop_table("assistant_sessions")

    op.drop_index(
        "ix_assistant_spec_versions_spec_version",
        table_name="assistant_spec_versions",
    )
    op.drop_index(
        "ix_assistant_spec_versions_spec_id",
        table_name="assistant_spec_versions",
    )
    op.drop_table("assistant_spec_versions")

    op.drop_index("ix_assistant_specs_project_id", table_name="assistant_specs")
    op.drop_index("ix_assistant_specs_workspace_id", table_name="assistant_specs")
    op.drop_index("ix_assistant_specs_owner_user_id", table_name="assistant_specs")
    op.drop_index("ix_assistant_specs_name", table_name="assistant_specs")
    op.drop_table("assistant_specs")
