"""Bot registry, versions, and deployment ORM models.

Backs :class:`aqp.bots.spec.BotSpec` (declarative) and
:class:`aqp.bots.runtime.BotRuntime` (execution + telemetry):

- ``bots`` — logical bot row (the latest active version of a named spec
  inside a project).
- ``bot_versions`` — immutable, hash-locked snapshot of every BotSpec
  the registry has ever seen for a given bot.
- ``bot_deployments`` — one row per deploy / backtest / paper / chat
  invocation; references the version that produced it so a run can be
  replayed against the exact spec it was built from.

All three tables are ``ProjectScopedMixin`` so the multi-tenant
ownership refactor (Alembic 0017–0019) covers them automatically.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Bot(Base, ProjectScopedMixin):
    """Logical bot — the latest active version of a named spec inside a project."""

    __tablename__ = "bots"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(240), nullable=False)
    slug = Column(String(120), nullable=False, index=True)
    kind = Column(String(32), nullable=False, default="trading", index=True)
    description = Column(Text, nullable=True)
    current_version = Column(Integer, nullable=False, default=1)
    spec_yaml = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    annotations = Column(JSON, default=list)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="uq_bots_project_slug"),
    )


class BotVersion(Base, ProjectScopedMixin):
    """Immutable, hash-locked snapshot of a :class:`Bot`'s spec."""

    __tablename__ = "bot_versions"
    id = Column(String(36), primary_key=True, default=_uuid)
    bot_id = Column(
        String(36),
        ForeignKey("bots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    spec_hash = Column(String(64), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    notes = Column(Text, nullable=True)
    created_by = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("bot_id", "spec_hash", name="uq_bot_versions_bot_hash"),
        UniqueConstraint("bot_id", "version", name="uq_bot_versions_bot_version"),
    )


Index("ix_bot_versions_bot_version", BotVersion.bot_id, BotVersion.version)


class BotDeployment(Base, ProjectScopedMixin):
    """One execution of a bot — backtest, paper session, chat, or k8s deploy."""

    __tablename__ = "bot_deployments"
    id = Column(String(36), primary_key=True, default=_uuid)
    bot_id = Column(
        String(36),
        ForeignKey("bots.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    version_id = Column(
        String(36),
        ForeignKey("bot_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target = Column(String(40), nullable=False, index=True)
    task_id = Column(String(120), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    manifest_yaml = Column(Text, nullable=True)
    result_summary = Column(JSON, default=dict)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    # AGENTS.md hard rule 34: every run-producing flow MUST stamp
    # ``experiment_id``. Migration 0037 already added the column +
    # FK + index; this ORM mirror lets ``BotRuntime`` deployments
    # carry the umbrella experiment id without falling off the
    # SQLAlchemy session.
    experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


Index("ix_bot_deployments_status_started", BotDeployment.status, BotDeployment.started_at)


# ---------------------------------------------------------------------------
# QuantBot Platform — event-sourced state (migration 0058)
# ---------------------------------------------------------------------------


class BotEvent(Base, ProjectScopedMixin):
    """Append-only event log for one bot.

    Partitioned monthly by ``recorded_at`` on PostgreSQL (see migration
    ``0058_bot_event_sourcing``). The composite primary key
    ``(bot_id, seq_no, recorded_at)`` is required for declarative
    partitioning; SQLite test environments drop the ``recorded_at``
    column from the PK transparently.

    Per AGENTS rule 34, ``experiment_id`` / ``test_id`` are stamped by
    :class:`LedgerWriter._stamp` from the active ``RequestContext``.
    """

    __tablename__ = "bot_events"
    bot_id = Column(String(36), primary_key=True, nullable=False)
    seq_no = Column(BigInteger, primary_key=True, nullable=False)
    recorded_at = Column(
        DateTime, primary_key=True, default=datetime.utcnow, nullable=False
    )
    event_type = Column(String(64), nullable=False)
    event_data = Column(JSON, nullable=False, default=dict)
    occurred_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    experiment_id = Column(String(36), nullable=True, index=True)
    test_id = Column(String(36), nullable=True, index=True)


Index("ix_bot_events_occurred_at_orm", BotEvent.occurred_at)


class BotOrderRow(Base, ProjectScopedMixin):
    """Order FSM row — one per ``client_order_id``.

    Tracks the canonical Order Lifecycle FSM (blueprint §G.1):
    ``CREATED -> VALIDATED -> ROUTED -> ACKNOWLEDGED ->
    PARTIALLY_FILLED -> FILLED`` plus the
    ``CANCEL_PENDING -> CANCELLED`` and terminal ``REJECTED`` /
    ``EXPIRED`` / ``DISPUTED`` branches.
    """

    __tablename__ = "bot_orders"
    id = Column(String(36), primary_key=True, default=_uuid)
    bot_id = Column(
        String(36),
        ForeignKey("bots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_order_id = Column(String(80), nullable=False, index=True)
    venue_order_id = Column(String(80), nullable=True, index=True)
    venue = Column(String(40), nullable=False, index=True)
    symbol = Column(String(80), nullable=False, index=True)
    side = Column(String(8), nullable=False)
    order_type = Column(String(16), nullable=False)
    time_in_force = Column(String(16), nullable=False, default="gtc")
    status = Column(String(32), nullable=False, index=True)
    quantity = Column(String(64), nullable=False)
    limit_price = Column(String(64), nullable=True)
    stop_price = Column(String(64), nullable=True)
    cumulative_qty = Column(String(64), nullable=False, default="0")
    avg_fill_price = Column(String(64), nullable=True)
    strategy_id = Column(String(80), nullable=True)
    parent_order_id = Column(String(80), nullable=True, index=True)
    correlation_id = Column(String(80), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    acknowledged_at = Column(DateTime, nullable=True)
    terminal_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    test_id = Column(
        String(36),
        ForeignKey("aqp_tests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        UniqueConstraint("bot_id", "client_order_id", name="uq_bot_orders_bot_coid"),
    )


class BotFillRow(Base, ProjectScopedMixin):
    """One fill on a bot order.

    Dedup key per blueprint §G.6:
    ``(venue, symbol, side, exec_id, trade_date, exec_type)``.
    Adapters MUST populate ``exec_id`` so a venue replay doesn't
    double-book the position.
    """

    __tablename__ = "bot_fills"
    id = Column(String(36), primary_key=True, default=_uuid)
    order_id = Column(
        String(36),
        ForeignKey("bot_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bot_id = Column(String(36), nullable=False, index=True)
    venue = Column(String(40), nullable=False)
    symbol = Column(String(80), nullable=False)
    side = Column(String(8), nullable=False)
    fill_qty = Column(String(64), nullable=False)
    fill_price = Column(String(64), nullable=False)
    cumulative_qty = Column(String(64), nullable=False)
    leaves_qty = Column(String(64), nullable=False, default="0")
    exec_id = Column(String(80), nullable=False)
    trade_date = Column(String(10), nullable=True)
    exec_type = Column(String(8), nullable=False, default="trade")
    liquidity = Column(String(16), nullable=False, default="unknown")
    fee = Column(String(64), nullable=False, default="0")
    fee_currency = Column(String(8), nullable=True)
    venue_ts = Column(DateTime, nullable=True)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "venue",
            "symbol",
            "side",
            "exec_id",
            "trade_date",
            "exec_type",
            name="uq_bot_fills_dedup",
        ),
    )


class BotSnapshot(Base, ProjectScopedMixin):
    """Periodic state snapshot — replay anchor.

    A snapshot lets the kernel skip replaying every event from the
    beginning of time when warming up; the kernel rebuilds in-memory
    state from the latest snapshot and replays ``bot_events`` with
    ``seq_no > snapshot.seq_no``.
    """

    __tablename__ = "bot_snapshots"
    id = Column(String(36), primary_key=True, default=_uuid)
    bot_id = Column(
        String(36),
        ForeignKey("bots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id = Column(String(80), nullable=True, index=True)
    seq_no = Column(BigInteger, nullable=False)
    snapshot_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    positions = Column(JSON, nullable=False, default=dict)
    exposures = Column(JSON, nullable=False, default=dict)
    metrics = Column(JSON, nullable=False, default=dict)
    raw_state = Column(JSON, nullable=False, default=dict)
    experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


Index("ix_bot_snapshots_bot_seq_orm", BotSnapshot.bot_id, BotSnapshot.seq_no)


__all__ = [
    "Bot",
    "BotDeployment",
    "BotEvent",
    "BotFillRow",
    "BotOrderRow",
    "BotSnapshot",
    "BotVersion",
]
