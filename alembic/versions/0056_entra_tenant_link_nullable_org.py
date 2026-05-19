"""Allow pending EntraTenantLink rows without an organization (AGENTS rule 44).

Revision ID: 0056_entra_tenant_link_nullable_org
Revises: 0055_workload_runs
Create Date: 2026-05-18

The original 0050 migration made ``entra_tenant_links.organization_id``
``NOT NULL``, but ``aqp.auth.user._apply_entra_tenant_link`` creates
``pending`` rows for unknown ``tid`` claims **before** an AQP
super-admin promotes them to an :class:`Organization`. This migration
relaxes the constraint so the pending lifecycle in AGENTS rule 44
actually works.

Promotion via ``POST /tenancy/entra-links/{id}/promote`` populates
``organization_id`` + flips ``status`` to ``active`` in one
transaction; the partial index on ``status='pending'`` (added below)
keeps queries selective.

Strictly additive in semantic terms — pre-existing rows with a real
``organization_id`` continue to work. Down-grade re-asserts the NOT
NULL only if no NULL values remain (otherwise raises so the operator
can decide).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0056_entra_tenant_link_nullable_org"
down_revision = "0055_workload_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Allow NULL for ``pending`` rows. We rely on the existing
    # ``status`` column to distinguish "awaiting promotion" from
    # "active link with org".
    op.alter_column(
        "entra_tenant_links",
        "organization_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )
    # Partial index keeps "pending" lookups fast on Postgres + SQLite.
    op.create_index(
        "ix_entra_tenant_links_pending",
        "entra_tenant_links",
        ["entra_tenant_id"],
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_entra_tenant_links_pending",
        table_name="entra_tenant_links",
    )
    # NB: down-revert ONLY succeeds when no NULL ``organization_id``
    # rows remain. Operators should promote / delete pending rows
    # first; we don't auto-delete here because pending links may be
    # legitimate work-in-progress.
    op.alter_column(
        "entra_tenant_links",
        "organization_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
