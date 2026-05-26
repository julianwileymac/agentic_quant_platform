"""AgentCore session columns on ``agent_runs_v2`` (Phase E of AWS hybrid).

Revision ID: 0087_agentcore_session_columns
Revises: 0086_lineage_cell_id
Create Date: 2026-05-25

When :class:`aqp.agents.runtime.AgentRuntime` is invoked with
``agentcore_runtime_alias=<alias>`` the run is dispatched via
``boto3.client('bedrock-agentcore').invoke_agent_runtime(...)`` instead
of the in-process CrewAI loop. The persisted ``agent_runs_v2`` row
gains three new columns so the operator UI + the replay harness can
trace the AgentCore session lifecycle:

- ``agentcore_session_id``  — opaque session id returned by AgentCore;
  used to thread short-term Memory events.
- ``agentcore_runtime_arn`` — the runtime ARN this run was dispatched
  through. Persisted so a config change to the SSM
  ``/aqp/${env}/agentcore_runtime_arn`` pointer doesn't lose replay
  fidelity.
- ``agentcore_memory_id``   — the Memory id this run wrote events to.
  Optional: when AgentCore Memory isn't enabled the column stays NULL.

Every column is nullable so existing rows keep validating without a
backfill. Per AGENTS rule 6 this migration is immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0087_agentcore_session_columns"
down_revision = "0086_lineage_cell_id"
branch_labels = None
depends_on = None


def _table_exists(bind: sa.engine.Connection, name: str) -> bool:
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    try:
        return any(c["name"] == column for c in insp.get_columns(table))
    except Exception:  # pragma: no cover - defensive
        return False


_NEW_COLUMNS: tuple[tuple[str, sa.types.TypeEngine, int | None], ...] = (
    ("agentcore_session_id", sa.String(128), 128),
    ("agentcore_runtime_arn", sa.String(512), 512),
    ("agentcore_memory_id", sa.String(128), 128),
)


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "agent_runs_v2"):
        return
    for name, column_type, _length in _NEW_COLUMNS:
        if _column_exists(bind, "agent_runs_v2", name):
            continue
        op.add_column(
            "agent_runs_v2",
            sa.Column(name, column_type, nullable=True),
        )

    # Replay queries hit ``agentcore_session_id`` directly when an
    # operator picks a session from the AgentCore inspector pane; only
    # the session id needs an index.
    if _column_exists(bind, "agent_runs_v2", "agentcore_session_id"):
        op.create_index(
            "ix_agent_runs_v2_agentcore_session_id",
            "agent_runs_v2",
            ["agentcore_session_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "agent_runs_v2"):
        return

    if _column_exists(bind, "agent_runs_v2", "agentcore_session_id"):
        try:
            op.drop_index(
                "ix_agent_runs_v2_agentcore_session_id",
                table_name="agent_runs_v2",
            )
        except Exception:  # pragma: no cover - defensive
            pass

    for name, _column_type, _length in _NEW_COLUMNS:
        if _column_exists(bind, "agent_runs_v2", name):
            op.drop_column("agent_runs_v2", name)
