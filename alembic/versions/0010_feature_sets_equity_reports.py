"""feature_sets, feature_set_versions, feature_set_usages, equity_reports

Revision ID: 0010_feature_sets_equity_reports
Revises: 0009_judge_replay_interrupts
Create Date: 2026-04-24

Adds persistence for the deep-research milestone:

- ``feature_sets`` + ``feature_set_versions`` + ``feature_set_usages`` —
  persistent named indicator / model-pred bundles shared across
  backtest / train / live / RL.
- ``equity_reports`` — FinRobot-style section-agent equity research
  reports.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_feature_sets_equity_reports"
down_revision = "0009_judge_replay_interrupts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_sets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="indicator"),
        sa.Column("specs", sa.JSON(), nullable=True),
        sa.Column("default_lookback_days", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
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
    op.create_index("ix_feature_sets_name", "feature_sets", ["name"], unique=True)
    op.create_index("ix_feature_sets_created_at", "feature_sets", ["created_at"])

    op.create_table(
        "feature_set_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "feature_set_id",
            sa.String(length=36),
            sa.ForeignKey("feature_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("specs", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_feature_set_versions_feature_set_id",
        "feature_set_versions",
        ["feature_set_id"],
    )
    op.create_index(
        "ix_feature_set_versions_fs_version",
        "feature_set_versions",
        ["feature_set_id", "version"],
    )

    op.create_table(
        "feature_set_usages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "feature_set_id",
            sa.String(length=36),
            sa.ForeignKey("feature_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("consumer_kind", sa.String(length=32), nullable=False),
        sa.Column("consumer_id", sa.String(length=64), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_feature_set_usages_feature_set_id",
        "feature_set_usages",
        ["feature_set_id"],
    )
    op.create_index(
        "ix_feature_set_usages_consumer_kind",
        "feature_set_usages",
        ["consumer_kind"],
    )
    op.create_index(
        "ix_feature_set_usages_consumer_id",
        "feature_set_usages",
        ["consumer_id"],
    )
    op.create_index(
        "ix_feature_set_usages_created_at",
        "feature_set_usages",
        ["created_at"],
    )

    op.create_table(
        "equity_reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("vt_symbol", sa.String(length=40), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("peers", sa.JSON(), nullable=True),
        sa.Column("sections", sa.JSON(), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("valuation", sa.JSON(), nullable=True),
        sa.Column("catalysts", sa.JSON(), nullable=True),
        sa.Column("sensitivity", sa.JSON(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="completed",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_equity_reports_vt_symbol", "equity_reports", ["vt_symbol"])
    op.create_index("ix_equity_reports_as_of", "equity_reports", ["as_of"])
    op.create_index("ix_equity_reports_created_at", "equity_reports", ["created_at"])
    op.create_index(
        "ix_equity_reports_symbol_asof",
        "equity_reports",
        ["vt_symbol", "as_of"],
    )


def downgrade() -> None:
    op.drop_index("ix_equity_reports_symbol_asof", "equity_reports")
    op.drop_index("ix_equity_reports_created_at", "equity_reports")
    op.drop_index("ix_equity_reports_as_of", "equity_reports")
    op.drop_index("ix_equity_reports_vt_symbol", "equity_reports")
    op.drop_table("equity_reports")

    op.drop_index("ix_feature_set_usages_created_at", "feature_set_usages")
    op.drop_index("ix_feature_set_usages_consumer_id", "feature_set_usages")
    op.drop_index("ix_feature_set_usages_consumer_kind", "feature_set_usages")
    op.drop_index("ix_feature_set_usages_feature_set_id", "feature_set_usages")
    op.drop_table("feature_set_usages")

    op.drop_index("ix_feature_set_versions_fs_version", "feature_set_versions")
    op.drop_index("ix_feature_set_versions_feature_set_id", "feature_set_versions")
    op.drop_table("feature_set_versions")

    op.drop_index("ix_feature_sets_created_at", "feature_sets")
    op.drop_index("ix_feature_sets_name", "feature_sets")
    op.drop_table("feature_sets")
