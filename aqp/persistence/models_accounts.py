"""Phase 3 persistence: accounts, balances, positions, reconciliation anomalies.

Reflects the schema added in migrations 0042 + 0043.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from aqp.persistence.models import Base, _uuid


class AccountRow(Base):
    """Persistent account row.

    The Phase 3 successor to the in-memory ``AccountData``. Identified
    by ``(venue, account_id)`` -- the natural key the venue mints --
    so reconciliation can route external events to the right account
    without an extra lookup.
    """

    __tablename__ = "accounts"
    id = Column(String(36), primary_key=True, default=_uuid)
    account_id = Column(String(120), nullable=False, index=True)
    venue = Column(String(32), nullable=False, index=True)
    gateway = Column(String(32), nullable=True)
    account_type = Column(String(32), nullable=False)
    # cash | margin | portfolio_margin | futures | crypto_spot |
    # crypto_deriv | betting
    oms_type = Column(String(16), nullable=False, default="netting")
    # netting | hedging
    allow_cash_positions = Column(Boolean, nullable=False, default=True)
    base_currency = Column(String(16), nullable=False, default="USD")
    nickname = Column(String(120), nullable=True)
    status = Column(String(24), nullable=False, default="active", index=True)
    is_paper = Column(Boolean, nullable=False, default=True, index=True)
    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id = Column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
        nullable=True,
    )
    owner_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    meta = Column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("venue", "account_id", name="uq_accounts_venue_account_id"),
    )


class AccountBalanceRow(Base):
    """Per-(currency, balance_kind) row.

    Closes the legacy "single cash float" failure mode by giving the
    risk engine explicit access to CASH vs MARGIN_INITIAL vs
    BUYING_POWER. Aggregating all of these onto a single number was
    the original sin that made the legacy ``AccountData`` unable to
    enforce ``max_gross_exposure`` against margin properly.
    """

    __tablename__ = "account_balances"
    id = Column(String(36), primary_key=True, default=_uuid)
    account_pk = Column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    currency = Column(String(16), nullable=False, index=True)
    balance_kind = Column(String(32), nullable=False, index=True)
    # CASH | MARGIN_INITIAL | MARGIN_MAINTENANCE | BUYING_POWER |
    # EXCESS_LIQUIDITY | UNREALIZED_PNL | REALIZED_PNL_DAY |
    # WITHDRAWABLE | LOCKED
    amount = Column(Float, nullable=False, default=0.0)
    snapshot_ts = Column(DateTime, nullable=False, default=datetime.utcnow)
    source = Column(String(32), nullable=True)
    # venue_rest | venue_ws | manager | sim
    meta = Column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "account_pk",
            "currency",
            "balance_kind",
            name="uq_account_balances_address",
        ),
    )


class AccountPositionRow(Base):
    """One position row.

    Keyed by the composite ``(account_pk, venue, vt_symbol,
    position_side)`` so hedge-mode venues (Binance, Bybit) can carry
    simultaneous LONG and SHORT rows on the same instrument. Netting
    venues use ``position_side='net'`` and only have one row per
    instrument.
    """

    __tablename__ = "account_positions"
    id = Column(String(36), primary_key=True, default=_uuid)
    account_pk = Column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    venue = Column(String(32), nullable=False, index=True)
    instrument_id = Column(
        String(36),
        ForeignKey("instruments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    vt_symbol = Column(String(64), nullable=False, index=True)
    position_side = Column(String(8), nullable=False, default="net")
    # net | long | short
    quantity = Column(Float, nullable=False, default=0.0)
    average_entry_price = Column(Float, nullable=True)
    market_price = Column(Float, nullable=True)
    unrealized_pnl = Column(Float, nullable=True)
    realized_pnl = Column(Float, nullable=True)
    leverage = Column(Float, nullable=True)
    liquidation_price = Column(Float, nullable=True)
    currency = Column(String(16), nullable=True)
    snapshot_ts = Column(DateTime, nullable=False, default=datetime.utcnow)
    source = Column(String(32), nullable=True)
    meta = Column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "account_pk",
            "venue",
            "vt_symbol",
            "position_side",
            name="uq_account_positions_composite_key",
        ),
        Index(
            "ix_account_positions_address",
            "account_pk",
            "venue",
            "vt_symbol",
        ),
    )


class ReconciliationAnomalyRow(Base):
    """Audit log for every venue/cache disagreement.

    The reconciliation engine writes a row here whenever it detects an
    anomaly, regardless of whether it resolved the discrepancy or
    raised it. Operators triage from this table.
    """

    __tablename__ = "reconciliation_anomalies"
    id = Column(String(36), primary_key=True, default=_uuid)
    account_id = Column(String(120), nullable=False, index=True)
    venue = Column(String(32), nullable=False, index=True)
    vt_symbol = Column(String(64), nullable=True)
    instrument_id = Column(
        String(36),
        ForeignKey("instruments.id", ondelete="SET NULL"),
        nullable=True,
    )
    position_side = Column(String(8), nullable=True)
    client_order_id = Column(String(64), nullable=True)
    venue_order_id = Column(String(120), nullable=True)
    venue_execution_id = Column(String(120), nullable=True)
    anomaly_kind = Column(String(32), nullable=False, index=True)
    # missing_in_cache | missing_at_venue | quantity_mismatch |
    # price_mismatch | duplicate_uuid | orphan_external_claim |
    # overfill_tolerated | status_mismatch
    severity = Column(String(16), nullable=False, default="warn", index=True)
    resolution = Column(String(32), nullable=False, index=True)
    # synthesised_external_claim | corrected_cache | logged_only |
    # raised_error | rolled_back
    cache_state = Column(JSON, default=dict)
    venue_state = Column(JSON, default=dict)
    delta = Column(JSON, default=dict)
    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id = Column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ts_detected = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    ts_resolved = Column(DateTime, nullable=True)
    meta = Column(JSON, default=dict)

    __table_args__ = (
        Index(
            "ix_reconciliation_anomalies_address",
            "account_id",
            "venue",
            "vt_symbol",
            "position_side",
        ),
    )


__all__ = [
    "AccountBalanceRow",
    "AccountPositionRow",
    "AccountRow",
    "ReconciliationAnomalyRow",
]
