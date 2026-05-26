"""Lineage v2 cell-awareness columns (Phase 7 §10.3).

Revision ID: 0086_lineage_cell_id
Revises: 0085_audit_lake_anchors
Create Date: 2026-05-25

Phase 3 §6.3 (Alembic 0083) already added ``cell_id`` to ``audit_log``,
``data_lineage_events``, and ``security_audit_events``. The bipartite
lineage v2 surface (Alembic 0059) has not been cell-aware yet because
the bus pre-dates the cell registry. This migration finishes the work
by adding ``cell_id`` to:

- ``lineage_dataset_vertex``
- ``lineage_transform_vertex``
- ``lineage_edge``
- ``lineage_openlineage_outbox``
- ``lineage_signing_key_archive``

Every column is nullable + FK-less (matching the audit_log+cell_id
shape from 0083) so existing rows keep validating. The lineage bus
fills the column from ``RequestContext.cell_id`` on every new event;
the bipartite observer (``aqp/lineage/observer.py``) writes the
column on subsequent flushes.

Per AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0086_lineage_cell_id"
down_revision = "0085_audit_lake_anchors"
branch_labels = None
depends_on = None


_LINEAGE_TABLES: tuple[str, ...] = (
    "lineage_dataset_vertex",
    "lineage_transform_vertex",
    "lineage_edge",
    "lineage_openlineage_outbox",
    "lineage_signing_key_archive",
)


def _table_exists(bind, name: str) -> bool:
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _column_exists(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    for table in _LINEAGE_TABLES:
        if not _table_exists(bind, table):
            continue
        if _column_exists(bind, table, "cell_id"):
            continue
        op.add_column(
            table,
            sa.Column(
                "cell_id",
                sa.String(120),
                nullable=True,
            ),
        )
        op.create_index(
            f"ix_{table}_cell_id", table, ["cell_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table in _LINEAGE_TABLES:
        if not _table_exists(bind, table):
            continue
        if not _column_exists(bind, table, "cell_id"):
            continue
        op.drop_index(f"ix_{table}_cell_id", table_name=table)
        op.drop_column(table, "cell_id")
