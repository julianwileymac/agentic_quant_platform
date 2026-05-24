"""User tiers, template catalog, audit-log (Phase 0 — Foundations, plan section 4).

Revision ID: 0069_user_tiers_template_catalog_audit
Revises: 0068_rl_ledger
Create Date: 2026-05-24

Last of four Phase 0 migrations. Creates three tables:

- ``user_tiers`` — joins users to a tier (free / starter / advanced /
  enterprise) that scales per-policy capacity for restricted endpoints.
- ``template_catalog`` — connector marketplace template catalog
  (Phase 5 seeds 50+ rows). Created now so the FK relationships are
  in place when later phases extend.
- ``audit_log`` — tamper-evident hash-chain audit log. Every row
  carries a ``hash`` (SHA-256 over the row contents) and ``prev_hash``
  pointing at the previous row's hash. Phase 6 nightly export ships
  to S3 with object lock for Reg SCI 17 CFR § 242.1005 + MiFID II
  Article 25 (7-year retention).

All three tables are workspace-scoped + RLS-protected by
``workspace_id`` per AGENTS rule 51.

Per AGENTS rule 6 (root): immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0069_user_tiers_template_catalog_audit"
down_revision = "0068_rl_ledger"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # user_tiers
    # ------------------------------------------------------------------
    op.create_table(
        "user_tiers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tier", sa.String(32), nullable=False, server_default="free"),
        sa.Column(
            "monthly_quota_multiplier",
            sa.Float,
            nullable=False,
            server_default="1.0",
        ),
        sa.Column("monthly_token_budget", sa.BigInteger, nullable=True),
        sa.Column(
            "effective_from",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("effective_until", sa.DateTime, nullable=True),
        sa.Column(
            "granted_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("meta", sa.JSON, nullable=False, server_default="{}"),
        sa.UniqueConstraint(
            "owner_user_id", "effective_from", name="uq_user_tiers_owner_from"
        ),
    )
    op.create_index(
        "ix_user_tiers_owner_user_id", "user_tiers", ["owner_user_id"]
    )
    op.create_index("ix_user_tiers_workspace_id", "user_tiers", ["workspace_id"])
    op.create_index("ix_user_tiers_tier", "user_tiers", ["tier"])

    # ------------------------------------------------------------------
    # template_catalog
    # ------------------------------------------------------------------
    op.create_table(
        "template_catalog",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("display_name", sa.String(240), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("vendor_tier", sa.String(32), nullable=True),
        sa.Column("spec_json", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("rate_limit_class", sa.String(120), nullable=True),
        sa.Column("default_sync_mode", sa.String(64), nullable=True),
        sa.Column("doc_url", sa.String(500), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_template_catalog_owner_user_id",
        "template_catalog",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_template_catalog_workspace_id",
        "template_catalog",
        ["workspace_id"],
    )
    op.create_index("ix_template_catalog_slug", "template_catalog", ["slug"])
    op.create_index("ix_template_catalog_kind", "template_catalog", ["kind"])
    op.create_index(
        "ix_template_catalog_rate_limit_class",
        "template_catalog",
        ["rate_limit_class"],
    )
    op.create_index(
        "ix_template_catalog_kind_active",
        "template_catalog",
        ["kind", "is_active"],
    )

    # ------------------------------------------------------------------
    # audit_log
    # ------------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            sa.BigInteger,
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "ts",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("event_category", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column(
            "actor_kind",
            sa.String(16),
            nullable=False,
            server_default="user",
        ),
        sa.Column("agent_subject", sa.String(255), nullable=True),
        sa.Column(
            "on_behalf_of_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tool_id", sa.String(120), nullable=True),
        sa.Column("approval_id", sa.String(36), nullable=True),
        sa.Column("template_id", sa.String(36), nullable=True),
        sa.Column("connection_id", sa.String(36), nullable=True),
        sa.Column("request_id", sa.String(36), nullable=True),
        sa.Column("details", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("prev_hash", sa.LargeBinary, nullable=True),
        sa.Column("hash", sa.LargeBinary, nullable=False),
    )
    op.create_index("ix_audit_log_owner_user_id", "audit_log", ["owner_user_id"])
    op.create_index("ix_audit_log_workspace_id", "audit_log", ["workspace_id"])
    op.create_index("ix_audit_log_ts", "audit_log", ["ts"])
    op.create_index(
        "ix_audit_log_event_category", "audit_log", ["event_category"]
    )
    op.create_index("ix_audit_log_event_type", "audit_log", ["event_type"])
    op.create_index("ix_audit_log_tool_id", "audit_log", ["tool_id"])
    op.create_index("ix_audit_log_approval_id", "audit_log", ["approval_id"])
    op.create_index(
        "ix_audit_log_owner_ts", "audit_log", ["owner_user_id", "ts"]
    )
    op.create_index(
        "ix_audit_log_event_category_ts",
        "audit_log",
        ["event_category", "ts"],
    )

    if not _is_postgres():
        return

    for table in ("user_tiers", "template_catalog", "audit_log"):
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
                    ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
                    ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
                    DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};
                    CREATE POLICY tenant_isolation_{table} ON {table}
                        USING (workspace_id IS NULL OR workspace_id =
                               current_setting('app.current_workspace_id', true));
                    GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO app_runtime;
                END IF;
            END
            $$;
            """
        )


def downgrade() -> None:
    if _is_postgres():
        for table in ("audit_log", "template_catalog", "user_tiers"):
            op.execute(
                f"""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = '{table}'
                    ) THEN
                        DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};
                        ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
                        ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
                    END IF;
                END
                $$;
                """
            )

    op.drop_index("ix_audit_log_event_category_ts", table_name="audit_log")
    op.drop_index("ix_audit_log_owner_ts", table_name="audit_log")
    op.drop_index("ix_audit_log_approval_id", table_name="audit_log")
    op.drop_index("ix_audit_log_tool_id", table_name="audit_log")
    op.drop_index("ix_audit_log_event_type", table_name="audit_log")
    op.drop_index("ix_audit_log_event_category", table_name="audit_log")
    op.drop_index("ix_audit_log_ts", table_name="audit_log")
    op.drop_index("ix_audit_log_workspace_id", table_name="audit_log")
    op.drop_index("ix_audit_log_owner_user_id", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index(
        "ix_template_catalog_kind_active", table_name="template_catalog"
    )
    op.drop_index(
        "ix_template_catalog_rate_limit_class", table_name="template_catalog"
    )
    op.drop_index("ix_template_catalog_kind", table_name="template_catalog")
    op.drop_index("ix_template_catalog_slug", table_name="template_catalog")
    op.drop_index(
        "ix_template_catalog_workspace_id", table_name="template_catalog"
    )
    op.drop_index(
        "ix_template_catalog_owner_user_id", table_name="template_catalog"
    )
    op.drop_table("template_catalog")

    op.drop_index("ix_user_tiers_tier", table_name="user_tiers")
    op.drop_index("ix_user_tiers_workspace_id", table_name="user_tiers")
    op.drop_index("ix_user_tiers_owner_user_id", table_name="user_tiers")
    op.drop_table("user_tiers")
