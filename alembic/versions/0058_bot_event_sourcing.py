"""Bot event sourcing: bot_events, bot_orders, bot_fills, bot_snapshots.

Revision ID: 0058_bot_event_sourcing
Revises: 0057_data_lab_foundation
Create Date: 2026-05-24

Phase 4 of the QuantBot Platform extension. Strictly additive — the
existing ``bots`` / ``bot_versions`` / ``bot_deployments`` tables
(migration ``0020_bots``) are untouched. The new tables capture the
event-sourced state of a running bot:

- ``bot_events`` — append-only event log. Partitioned by month on
  ``recorded_at`` per blueprint §H.2. GIN index on the JSONB payload.
- ``bot_orders`` — Order FSM rows (one per ``client_order_id``).
- ``bot_fills`` — Fill detail rows. Dedup key is
  ``(trade_date, exec_id, symbol, side, exec_type)`` per blueprint
  §G.6 — adapters MUST populate ``exec_id``.
- ``bot_snapshots`` — periodic state snapshots (replay anchors).

Tenancy / governance hooks per AGENTS:

- Every row carries ``owner_user_id`` / ``workspace_id`` / ``project_id``
  (ProjectScopedMixin columns).
- ``bot_orders`` and ``bot_snapshots`` carry ``experiment_id`` /
  ``test_id`` FKs per AGENTS rule 34. :class:`LedgerWriter._stamp`
  populates them from the active ``RequestContext`` automatically.

Partitioning notes (PostgreSQL):

- ``bot_events`` is declared ``PARTITION BY RANGE (recorded_at)``.
- One partition per UTC month, named ``bot_events_YYYY_MM``.
- A future Celery beat task (Phase 12) creates the next two months'
  partitions ahead of time. This migration creates the partitioned
  parent + the current month + the next month at upgrade time.

SQLite test environments fall back to a non-partitioned table; the
ORM-level code paths are identical and partition pruning is a no-op.

AGENTS rule 6: this migration is **immutable** once shipped.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0058_bot_event_sourcing"
down_revision = "0057_data_lab_foundation"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    """True iff we're running against a real PostgreSQL backend."""
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def _month_partition_name(when: datetime) -> str:
    return f"bot_events_{when.year:04d}_{when.month:02d}"


def _month_bounds(when: datetime) -> tuple[datetime, datetime]:
    """First-of-month and first-of-next-month, both UTC midnight."""
    start = datetime(when.year, when.month, 1, tzinfo=timezone.utc)
    if when.month == 12:
        end = datetime(when.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(when.year, when.month + 1, 1, tzinfo=timezone.utc)
    return start, end


def upgrade() -> None:
    is_pg = _is_postgres()

    # ------------------------------------------------------------------
    # bot_events (partitioned on PostgreSQL, plain on SQLite)
    # ------------------------------------------------------------------
    if is_pg:
        op.execute(
            """
            CREATE TABLE bot_events (
                bot_id        VARCHAR(36) NOT NULL,
                seq_no        BIGINT NOT NULL,
                event_type    VARCHAR(64) NOT NULL,
                event_data    JSONB NOT NULL,
                occurred_at   TIMESTAMPTZ NOT NULL,
                recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                owner_user_id VARCHAR(80),
                workspace_id  VARCHAR(80),
                project_id    VARCHAR(80),
                experiment_id VARCHAR(36),
                test_id       VARCHAR(36),
                PRIMARY KEY (bot_id, seq_no, recorded_at)
            ) PARTITION BY RANGE (recorded_at);
            """
        )
        op.execute(
            "CREATE INDEX ix_bot_events_data_gin ON bot_events USING GIN (event_data);"
        )
        op.execute(
            "CREATE INDEX ix_bot_events_bot_seq ON bot_events (bot_id, seq_no);"
        )
        op.execute(
            "CREATE INDEX ix_bot_events_occurred_at ON bot_events (occurred_at);"
        )
        # Pre-create this month and next month.
        now = datetime.now(timezone.utc)
        for offset in (0, 1):
            target = now.replace(day=15) + timedelta(days=30 * offset)
            start, end = _month_bounds(target)
            name = _month_partition_name(target)
            op.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {name}
                PARTITION OF bot_events
                FOR VALUES FROM ('{start.isoformat()}')
                TO ('{end.isoformat()}');
                """
            )
    else:
        op.create_table(
            "bot_events",
            sa.Column("bot_id", sa.String(36), nullable=False),
            sa.Column("seq_no", sa.BigInteger, nullable=False),
            sa.Column("event_type", sa.String(64), nullable=False),
            sa.Column("event_data", sa.JSON, nullable=False),
            sa.Column("occurred_at", sa.DateTime, nullable=False),
            sa.Column(
                "recorded_at",
                sa.DateTime,
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("owner_user_id", sa.String(80), nullable=True),
            sa.Column("workspace_id", sa.String(80), nullable=True),
            sa.Column("project_id", sa.String(80), nullable=True),
            sa.Column("experiment_id", sa.String(36), nullable=True),
            sa.Column("test_id", sa.String(36), nullable=True),
            sa.PrimaryKeyConstraint("bot_id", "seq_no"),
        )
        op.create_index("ix_bot_events_bot_seq", "bot_events", ["bot_id", "seq_no"])
        op.create_index("ix_bot_events_occurred_at", "bot_events", ["occurred_at"])

    # ------------------------------------------------------------------
    # bot_orders (Order FSM rows)
    # ------------------------------------------------------------------
    op.create_table(
        "bot_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "bot_id",
            sa.String(36),
            sa.ForeignKey("bots.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("client_order_id", sa.String(80), nullable=False, index=True),
        sa.Column("venue_order_id", sa.String(80), nullable=True, index=True),
        sa.Column("venue", sa.String(40), nullable=False, index=True),
        sa.Column("symbol", sa.String(80), nullable=False, index=True),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("order_type", sa.String(16), nullable=False),
        sa.Column("time_in_force", sa.String(16), nullable=False, server_default="gtc"),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("quantity", sa.Numeric(38, 18), nullable=False),
        sa.Column("limit_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("stop_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("cumulative_qty", sa.Numeric(38, 18), nullable=False, server_default="0"),
        sa.Column("avg_fill_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("strategy_id", sa.String(80), nullable=True),
        sa.Column("parent_order_id", sa.String(80), nullable=True, index=True),
        sa.Column("correlation_id", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("acknowledged_at", sa.DateTime, nullable=True),
        sa.Column("terminal_at", sa.DateTime, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("owner_user_id", sa.String(80), nullable=True),
        sa.Column("workspace_id", sa.String(80), nullable=True),
        sa.Column("project_id", sa.String(80), nullable=True),
        sa.Column(
            "experiment_id",
            sa.String(36),
            sa.ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "test_id",
            sa.String(36),
            sa.ForeignKey("aqp_tests.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.UniqueConstraint("bot_id", "client_order_id", name="uq_bot_orders_bot_coid"),
    )
    op.create_index(
        "ix_bot_orders_bot_status", "bot_orders", ["bot_id", "status"]
    )
    op.create_index(
        "ix_bot_orders_venue_symbol", "bot_orders", ["venue", "symbol"]
    )

    # ------------------------------------------------------------------
    # bot_fills (per-fill detail; dedup key on (trade_date, exec_id, …))
    # ------------------------------------------------------------------
    op.create_table(
        "bot_fills",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "order_id",
            sa.String(36),
            sa.ForeignKey("bot_orders.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("bot_id", sa.String(36), nullable=False, index=True),
        sa.Column("venue", sa.String(40), nullable=False),
        sa.Column("symbol", sa.String(80), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("fill_qty", sa.Numeric(38, 18), nullable=False),
        sa.Column("fill_price", sa.Numeric(38, 18), nullable=False),
        sa.Column("cumulative_qty", sa.Numeric(38, 18), nullable=False),
        sa.Column("leaves_qty", sa.Numeric(38, 18), nullable=False, server_default="0"),
        sa.Column("exec_id", sa.String(80), nullable=False),
        sa.Column("trade_date", sa.String(10), nullable=True),
        sa.Column("exec_type", sa.String(8), nullable=False, server_default="trade"),
        sa.Column("liquidity", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("fee", sa.Numeric(38, 18), nullable=False, server_default="0"),
        sa.Column("fee_currency", sa.String(8), nullable=True),
        sa.Column("venue_ts", sa.DateTime, nullable=True),
        sa.Column("recorded_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("owner_user_id", sa.String(80), nullable=True),
        sa.Column("workspace_id", sa.String(80), nullable=True),
        sa.Column("project_id", sa.String(80), nullable=True),
        sa.UniqueConstraint(
            "venue",
            "symbol",
            "side",
            "exec_id",
            "trade_date",
            "exec_type",
            name="uq_bot_fills_dedup",
        ),
    )
    op.create_index("ix_bot_fills_bot_recorded", "bot_fills", ["bot_id", "recorded_at"])

    # ------------------------------------------------------------------
    # bot_snapshots (replay anchors)
    # ------------------------------------------------------------------
    op.create_table(
        "bot_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "bot_id",
            sa.String(36),
            sa.ForeignKey("bots.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("run_id", sa.String(80), nullable=True, index=True),
        sa.Column("seq_no", sa.BigInteger, nullable=False),
        sa.Column("snapshot_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column(
            "positions",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON, "sqlite"),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "exposures",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON, "sqlite"),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON, "sqlite"),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "raw_state",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON, "sqlite"),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("owner_user_id", sa.String(80), nullable=True),
        sa.Column("workspace_id", sa.String(80), nullable=True),
        sa.Column("project_id", sa.String(80), nullable=True),
        sa.Column(
            "experiment_id",
            sa.String(36),
            sa.ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    op.create_index(
        "ix_bot_snapshots_bot_seq", "bot_snapshots", ["bot_id", "seq_no"]
    )


def downgrade() -> None:
    # Hard rule: migrations are immutable once shipped. Downgrade exists
    # only for development scaffolding; production never executes it.
    op.drop_index("ix_bot_snapshots_bot_seq", table_name="bot_snapshots")
    op.drop_table("bot_snapshots")
    op.drop_index("ix_bot_fills_bot_recorded", table_name="bot_fills")
    op.drop_table("bot_fills")
    op.drop_index("ix_bot_orders_venue_symbol", table_name="bot_orders")
    op.drop_index("ix_bot_orders_bot_status", table_name="bot_orders")
    op.drop_table("bot_orders")
    if _is_postgres():
        op.execute("DROP TABLE IF EXISTS bot_events CASCADE;")
    else:
        op.drop_index("ix_bot_events_occurred_at", table_name="bot_events")
        op.drop_index("ix_bot_events_bot_seq", table_name="bot_events")
        op.drop_table("bot_events")
