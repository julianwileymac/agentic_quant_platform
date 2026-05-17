"""Phase 3: reconciliation anomaly log.

Revision ID: 0043_reconciliation_anomalies
Revises: 0042_accounts_balances
Create Date: 2026-05-16

Captures every "venue and cache disagree" event the
:class:`aqp.trading.reconciliation.ReconciliationEngine` discovers. The
engine MAY suppress the error and continue (when ``allow_overfills`` is
on for the account) but it ALWAYS records a row here so an operator
can investigate later.

The row carries:

* The composite key the engine uses internally
  (``account_id``, ``venue``, ``vt_symbol``, ``position_side``)
* The discrepancy kind (``missing_in_cache`` |
  ``missing_at_venue`` | ``quantity_mismatch`` |
  ``price_mismatch`` | ``duplicate_uuid`` | ``orphan_external_claim``)
* The local + venue snapshots that diverged
* The resolution action the engine took
  (``synthesised_external_claim`` | ``corrected_cache`` |
  ``logged_only`` | ``raised_error``)

The row is intentionally lightweight: every detail not needed for
operator triage lives in the ``meta`` JSON column.

AGENTS rule 6: this migration is **immutable** once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0043_reconciliation_anomalies"
down_revision = "0042_accounts_balances"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reconciliation_anomalies",
        sa.Column("id", sa.String(length=36), nullable=False),
        # Composite address (matches the engine's state map key)
        sa.Column("account_id", sa.String(length=120), nullable=False),
        sa.Column("venue", sa.String(length=32), nullable=False),
        sa.Column("vt_symbol", sa.String(length=64), nullable=True),
        sa.Column("instrument_id", sa.String(length=36), nullable=True),
        sa.Column("position_side", sa.String(length=8), nullable=True),
        sa.Column("client_order_id", sa.String(length=64), nullable=True),
        sa.Column("venue_order_id", sa.String(length=120), nullable=True),
        sa.Column("venue_execution_id", sa.String(length=120), nullable=True),
        # Discrepancy classification
        sa.Column("anomaly_kind", sa.String(length=32), nullable=False),
        # missing_in_cache | missing_at_venue | quantity_mismatch |
        # price_mismatch | duplicate_uuid | orphan_external_claim |
        # overfill_tolerated | status_mismatch
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="warn"),
        # info | warn | error | critical
        sa.Column("resolution", sa.String(length=32), nullable=False),
        # synthesised_external_claim | corrected_cache | logged_only |
        # raised_error | rolled_back
        # The state both sides observed at the time of detection
        sa.Column("cache_state", sa.JSON(), nullable=True),
        sa.Column("venue_state", sa.JSON(), nullable=True),
        sa.Column("delta", sa.JSON(), nullable=True),
        # Tenancy + experiment linkage
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("experiment_id", sa.String(length=36), nullable=True),
        sa.Column("ts_detected", sa.DateTime(), nullable=False),
        sa.Column("ts_resolved", sa.DateTime(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["aqp_experiments.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reconciliation_anomalies_account_id",
        "reconciliation_anomalies",
        ["account_id"],
    )
    op.create_index(
        "ix_reconciliation_anomalies_venue",
        "reconciliation_anomalies",
        ["venue"],
    )
    op.create_index(
        "ix_reconciliation_anomalies_kind",
        "reconciliation_anomalies",
        ["anomaly_kind"],
    )
    op.create_index(
        "ix_reconciliation_anomalies_severity",
        "reconciliation_anomalies",
        ["severity"],
    )
    op.create_index(
        "ix_reconciliation_anomalies_resolution",
        "reconciliation_anomalies",
        ["resolution"],
    )
    op.create_index(
        "ix_reconciliation_anomalies_ts_detected",
        "reconciliation_anomalies",
        ["ts_detected"],
    )
    op.create_index(
        "ix_reconciliation_anomalies_workspace_id",
        "reconciliation_anomalies",
        ["workspace_id"],
    )
    op.create_index(
        "ix_reconciliation_anomalies_experiment_id",
        "reconciliation_anomalies",
        ["experiment_id"],
    )
    op.create_index(
        "ix_reconciliation_anomalies_address",
        "reconciliation_anomalies",
        ["account_id", "venue", "vt_symbol", "position_side"],
    )


def downgrade() -> None:
    op.drop_index("ix_reconciliation_anomalies_address", table_name="reconciliation_anomalies")
    op.drop_index(
        "ix_reconciliation_anomalies_experiment_id",
        table_name="reconciliation_anomalies",
    )
    op.drop_index(
        "ix_reconciliation_anomalies_workspace_id",
        table_name="reconciliation_anomalies",
    )
    op.drop_index(
        "ix_reconciliation_anomalies_ts_detected",
        table_name="reconciliation_anomalies",
    )
    op.drop_index(
        "ix_reconciliation_anomalies_resolution",
        table_name="reconciliation_anomalies",
    )
    op.drop_index(
        "ix_reconciliation_anomalies_severity",
        table_name="reconciliation_anomalies",
    )
    op.drop_index(
        "ix_reconciliation_anomalies_kind",
        table_name="reconciliation_anomalies",
    )
    op.drop_index(
        "ix_reconciliation_anomalies_venue", table_name="reconciliation_anomalies"
    )
    op.drop_index(
        "ix_reconciliation_anomalies_account_id",
        table_name="reconciliation_anomalies",
    )
    op.drop_table("reconciliation_anomalies")
