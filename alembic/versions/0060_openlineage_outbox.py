"""OpenLineage outbox table for the Marquez relay (Workstream B).

Revision ID: 0060_openlineage_outbox
Revises: 0059_lineage_graph_v2
Create Date: 2026-05-24

Adds one new table: ``lineage_openlineage_outbox``. Every
:class:`LineageEvent` flowing through :class:`LineageBus` results in
one row here when ``AQP_LINEAGE_OPENLINEAGE_RELAY_ENABLED=true``. A
Celery beat task (``aqp.tasks.openlineage_relay_tasks.drain_openlineage_outbox``)
POSTs each pending row's payload to Marquez and marks it ``sent_at``.

AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0060_openlineage_outbox"
down_revision = "0059_lineage_graph_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lineage_openlineage_outbox",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("eventType", sa.String(32), nullable=False),
        sa.Column("job_namespace", sa.String(120), nullable=False),
        sa.Column("job_name", sa.String(240), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("sent_at", sa.DateTime, nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_lineage_openlineage_outbox_event_type",
        "lineage_openlineage_outbox",
        ["eventType"],
    )
    op.create_index(
        "ix_lineage_openlineage_outbox_job",
        "lineage_openlineage_outbox",
        ["job_namespace", "job_name"],
    )
    op.create_index(
        "ix_lineage_openlineage_outbox_run",
        "lineage_openlineage_outbox",
        ["run_id"],
    )
    op.create_index(
        "ix_lineage_openlineage_outbox_created",
        "lineage_openlineage_outbox",
        ["created_at"],
    )
    op.create_index(
        "ix_lineage_openlineage_outbox_sent",
        "lineage_openlineage_outbox",
        ["sent_at"],
    )
    op.create_index(
        "ix_lineage_openlineage_outbox_pending",
        "lineage_openlineage_outbox",
        ["sent_at", "created_at"],
    )


def downgrade() -> None:
    for ix in (
        "ix_lineage_openlineage_outbox_pending",
        "ix_lineage_openlineage_outbox_sent",
        "ix_lineage_openlineage_outbox_created",
        "ix_lineage_openlineage_outbox_run",
        "ix_lineage_openlineage_outbox_job",
        "ix_lineage_openlineage_outbox_event_type",
    ):
        op.drop_index(ix, table_name="lineage_openlineage_outbox")
    op.drop_table("lineage_openlineage_outbox")
