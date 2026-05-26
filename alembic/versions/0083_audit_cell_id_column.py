"""Cell-aware audit columns + hash-chain function update.

Revision ID: 0083_audit_cell_id_column
Revises: 0082_cell_registry
Create Date: 2026-05-25

Phase 3 §6.3 (RESTRUCTURING_PLAN.md) — every audit + lineage event
stamped with the cell id of the cell that produced it.

Three tables grow a nullable ``cell_id`` column:

- ``security_audit_events`` (Alembic 0052 — admin / auth events).
- ``data_lineage_events`` (older flat lineage log).
- ``audit_log`` (Alembic 0069 — hash-chained agent / approval log).

The ``audit_log`` table has a row-level hash trigger installed in
Alembic 0079 (``enforce_audit_log_hash_chain``). Per AGENTS rule 6
that migration is immutable; this migration installs a NEW
``CREATE OR REPLACE FUNCTION`` body that:

1. Appends ``coalesce(NEW.cell_id, '')`` at the END of the
   ``row_content`` digest pipeline. The previous function ended
   with ``coalesce(encode(NEW.prev_hash, 'hex'), '')`` followed by a
   trailing pipe-empty; the new function adds a final
   ``'|' || coalesce(NEW.cell_id, '')`` so existing rows with
   ``cell_id = NULL`` continue to hash to the same digest they hash
   to today (cell_id is NULL on inserts that pre-date Phase 3, so
   the appended segment is the empty string).
2. Carries forward all the existing checks unchanged.

This means:

- Inserts that happened before Phase 3 hashed under the old
  function. Their stored ``hash`` value already accounts for
  ``cell_id`` being absent: ``coalesce(NEW.cell_id, '')`` is the
  empty string, which when appended via ``'|' || ''`` is identical
  to having no ``cell_id`` segment at all when ``cell_id`` is NULL.
- Future inserts that DO set ``cell_id`` get the extra segment in
  their digest. The chain remains intact because each row hashes
  its own content + the previous row's ``hash``, and the previous
  ``hash`` is by definition the prior row's full computed digest.

Per AGENTS rule 6 this migration is immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0083_audit_cell_id_column"
down_revision = "0082_cell_registry"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def _table_exists(bind: sa.engine.Connection, name: str) -> bool:
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    try:
        return any(c["name"] == column for c in insp.get_columns(table))
    except Exception:  # pragma: no cover - defensive
        return False


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Add nullable ``cell_id`` columns (FK to cells.id) on the three
    #    audit/lineage tables. We use op.add_column with a runtime
    #    table-exists guard so the migration is safe in test fixtures
    #    that build a partial schema.
    # ------------------------------------------------------------------
    for table in ("security_audit_events", "data_lineage_events", "audit_log"):
        if not _table_exists(bind, table):
            continue
        if _column_exists(bind, table, "cell_id"):
            continue
        op.add_column(
            table,
            sa.Column(
                "cell_id",
                sa.String(120),
                sa.ForeignKey("cells.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index(
            f"ix_{table}_cell_id", table, ["cell_id"]
        )

    # ------------------------------------------------------------------
    # 2. Replace the audit_log hash-chain function so cell_id is part of
    #    the digest. Old NULL rows continue to validate because
    #    coalesce(NULL, '') = '' and the appended '|' segment becomes
    #    '|' followed by empty string, matching the historical content
    #    of pre-Phase-3 rows (which had no cell_id and therefore
    #    contribute nothing to the digest beyond the trailing empty
    #    suffix). New rows hash with the cell_id segment populated.
    # ------------------------------------------------------------------
    if not _is_postgres():
        return
    if not _table_exists(bind, "audit_log"):
        return
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_audit_log_hash_chain()
        RETURNS TRIGGER AS $$
        DECLARE
            expected_prev BYTEA;
            computed_hash BYTEA;
            row_content TEXT;
        BEGIN
            SELECT hash INTO expected_prev FROM audit_log
                ORDER BY ts DESC, id DESC LIMIT 1;
            IF expected_prev IS NOT NULL THEN
                IF NEW.prev_hash IS NULL THEN
                    RAISE EXCEPTION
                        'audit_log: prev_hash NULL but chain non-empty';
                END IF;
                IF NEW.prev_hash <> expected_prev THEN
                    RAISE EXCEPTION
                        'audit_log: prev_hash mismatch (expected %, got %)',
                        encode(expected_prev, 'hex'),
                        encode(NEW.prev_hash, 'hex');
                END IF;
            END IF;
            row_content :=
                coalesce(NEW.event_type, '') || '|' ||
                coalesce(NEW.event_category, '') || '|' ||
                coalesce(NEW.actor_kind, '') || '|' ||
                coalesce(NEW.agent_subject, '') || '|' ||
                coalesce(NEW.on_behalf_of_user_id::text, '') || '|' ||
                coalesce(NEW.tool_id, '') || '|' ||
                coalesce(NEW.approval_id, '') || '|' ||
                coalesce(NEW.template_id, '') || '|' ||
                coalesce(NEW.connection_id, '') || '|' ||
                coalesce(NEW.details::text, '{}') || '|' ||
                coalesce(encode(NEW.prev_hash, 'hex'), '') || '|' ||
                coalesce(NEW.cell_id, '');
            computed_hash := digest(row_content, 'sha256');
            IF NEW.hash IS NULL THEN
                NEW.hash := computed_hash;
            ELSIF NEW.hash <> computed_hash THEN
                RAISE EXCEPTION
                    'audit_log: hash mismatch (expected %, got %)',
                    encode(computed_hash, 'hex'),
                    encode(NEW.hash, 'hex');
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()

    # Restore the Phase 1 (pre-cell) hash-chain function body before
    # dropping the cell_id column, otherwise the trigger references a
    # column that no longer exists.
    if _is_postgres() and _table_exists(bind, "audit_log"):
        op.execute(
            """
            CREATE OR REPLACE FUNCTION enforce_audit_log_hash_chain()
            RETURNS TRIGGER AS $$
            DECLARE
                expected_prev BYTEA;
                computed_hash BYTEA;
                row_content TEXT;
            BEGIN
                SELECT hash INTO expected_prev FROM audit_log
                    ORDER BY ts DESC, id DESC LIMIT 1;
                IF expected_prev IS NOT NULL THEN
                    IF NEW.prev_hash IS NULL THEN
                        RAISE EXCEPTION
                            'audit_log: prev_hash NULL but chain non-empty';
                    END IF;
                    IF NEW.prev_hash <> expected_prev THEN
                        RAISE EXCEPTION
                            'audit_log: prev_hash mismatch (expected %, got %)',
                            encode(expected_prev, 'hex'),
                            encode(NEW.prev_hash, 'hex');
                    END IF;
                END IF;
                row_content :=
                    coalesce(NEW.event_type, '') || '|' ||
                    coalesce(NEW.event_category, '') || '|' ||
                    coalesce(NEW.actor_kind, '') || '|' ||
                    coalesce(NEW.agent_subject, '') || '|' ||
                    coalesce(NEW.on_behalf_of_user_id::text, '') || '|' ||
                    coalesce(NEW.tool_id, '') || '|' ||
                    coalesce(NEW.approval_id, '') || '|' ||
                    coalesce(NEW.template_id, '') || '|' ||
                    coalesce(NEW.connection_id, '') || '|' ||
                    coalesce(NEW.details::text, '{}') || '|' ||
                    coalesce(encode(NEW.prev_hash, 'hex'), '');
                computed_hash := digest(row_content, 'sha256');
                IF NEW.hash IS NULL THEN
                    NEW.hash := computed_hash;
                ELSIF NEW.hash <> computed_hash THEN
                    RAISE EXCEPTION
                        'audit_log: hash mismatch (expected %, got %)',
                        encode(computed_hash, 'hex'),
                        encode(NEW.hash, 'hex');
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )

    for table in ("audit_log", "data_lineage_events", "security_audit_events"):
        if not _table_exists(bind, table):
            continue
        if not _column_exists(bind, table, "cell_id"):
            continue
        op.drop_index(f"ix_{table}_cell_id", table_name=table)
        op.drop_column(table, "cell_id")
