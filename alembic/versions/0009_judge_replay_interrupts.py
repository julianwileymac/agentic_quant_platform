"""agent judge reports + replay runs + backtest interrupts

Revision ID: 0009_judge_replay_interrupts
Revises: 0008_domain_model_expansion
Create Date: 2026-04-24

Adds the persistence required for the Interactive Agent Backtest UX:

- ``agent_judge_reports`` — LLM/agent-as-judge critiques over a
  backtest's decision trace.
- ``agent_replay_runs`` — counterfactual reruns linking an original
  backtest to a child backtest with a JSON diff of edited decisions.
- ``backtest_interrupts`` — Phase-2 scaffold for live mid-backtest HITL
  pause/resume.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_judge_replay_interrupts"
down_revision = "0008_domain_model_expansion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_judge_reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "backtest_id",
            sa.String(length=36),
            sa.ForeignKey("backtest_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "judge_class",
            sa.String(length=64),
            nullable=False,
            server_default="LLMJudge",
        ),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("findings", sa.JSON(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("rubric", sa.String(length=64), nullable=True, server_default="default"),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_agent_judge_reports_backtest_id",
        "agent_judge_reports",
        ["backtest_id"],
    )
    op.create_index(
        "ix_agent_judge_reports_created_at",
        "agent_judge_reports",
        ["created_at"],
    )
    op.create_index(
        "ix_agent_judge_reports_backtest_judge",
        "agent_judge_reports",
        ["backtest_id", "judge_class"],
    )

    op.create_table(
        "agent_replay_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "parent_backtest_id",
            sa.String(length=36),
            sa.ForeignKey("backtest_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "child_backtest_id",
            sa.String(length=36),
            sa.ForeignKey("backtest_runs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "judge_report_id",
            sa.String(length=36),
            sa.ForeignKey("agent_judge_reports.id"),
            nullable=True,
        ),
        sa.Column("edits", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_agent_replay_runs_parent_backtest_id",
        "agent_replay_runs",
        ["parent_backtest_id"],
    )
    op.create_index(
        "ix_agent_replay_runs_child_backtest_id",
        "agent_replay_runs",
        ["child_backtest_id"],
    )
    op.create_index(
        "ix_agent_replay_runs_judge_report_id",
        "agent_replay_runs",
        ["judge_report_id"],
    )
    op.create_index(
        "ix_agent_replay_runs_created_at",
        "agent_replay_runs",
        ["created_at"],
    )

    op.create_table(
        "backtest_interrupts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "backtest_id",
            sa.String(length=36),
            sa.ForeignKey("backtest_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column(
            "ts",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("rule", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_backtest_interrupts_backtest_id",
        "backtest_interrupts",
        ["backtest_id"],
    )
    op.create_index(
        "ix_backtest_interrupts_task_id",
        "backtest_interrupts",
        ["task_id"],
    )
    op.create_index(
        "ix_backtest_interrupts_ts",
        "backtest_interrupts",
        ["ts"],
    )
    op.create_index(
        "ix_backtest_interrupts_status",
        "backtest_interrupts",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_backtest_interrupts_status", "backtest_interrupts")
    op.drop_index("ix_backtest_interrupts_ts", "backtest_interrupts")
    op.drop_index("ix_backtest_interrupts_task_id", "backtest_interrupts")
    op.drop_index("ix_backtest_interrupts_backtest_id", "backtest_interrupts")
    op.drop_table("backtest_interrupts")

    op.drop_index("ix_agent_replay_runs_created_at", "agent_replay_runs")
    op.drop_index("ix_agent_replay_runs_judge_report_id", "agent_replay_runs")
    op.drop_index("ix_agent_replay_runs_child_backtest_id", "agent_replay_runs")
    op.drop_index("ix_agent_replay_runs_parent_backtest_id", "agent_replay_runs")
    op.drop_table("agent_replay_runs")

    op.drop_index("ix_agent_judge_reports_backtest_judge", "agent_judge_reports")
    op.drop_index("ix_agent_judge_reports_created_at", "agent_judge_reports")
    op.drop_index("ix_agent_judge_reports_backtest_id", "agent_judge_reports")
    op.drop_table("agent_judge_reports")
