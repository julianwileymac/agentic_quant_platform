"""Audit-log hash-chain enforcement trigger (Phase 6, plan section 10).

Revision ID: 0079_audit_log_hash_chain
Revises: 0078_replay_cache_entries
Create Date: 2026-05-24

The Phase 0 ``audit_log`` table (Alembic 0069) already has
``hash`` + ``prev_hash`` columns; Phase 6 installs a Postgres
trigger that enforces:

1. Every insert's ``prev_hash`` matches the most-recent row's
   ``hash``, OR the row is the first row.
2. The hash itself is computed deterministically from the row's
   immutable content (server-side, so an application-level bug
   cannot lie about the chain).

The trigger surfaces a clear error on violation so an operator
who reseeds out-of-order spots the break instantly.

Per AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

from alembic import op

revision = "0079_audit_log_hash_chain"
down_revision = "0078_replay_cache_entries"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
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
    op.execute(
        """
        DROP TRIGGER IF EXISTS audit_log_hash_chain ON audit_log;
        CREATE TRIGGER audit_log_hash_chain
            BEFORE INSERT ON audit_log
            FOR EACH ROW
            EXECUTE FUNCTION enforce_audit_log_hash_chain();
        """
    )


def downgrade() -> None:
    if not _is_postgres():
        return
    op.execute("DROP TRIGGER IF EXISTS audit_log_hash_chain ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS enforce_audit_log_hash_chain();")
