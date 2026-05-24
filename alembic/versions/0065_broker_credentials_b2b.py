"""Broker credentials + billing + per-org IdP tables (AGENTS rules 55 + B2B).

Revision ID: 0065_broker_credentials_b2b
Revises: 0064_schema_per_tenant_bootstrap
Create Date: 2026-05-24

Phase 5 of the Auth0 Refactor (AGENTS hard rules 52-55).

Adds five tables + one column:

- ``broker_credentials`` — per-user, envelope-encrypted broker API
  credentials. RLS-protected by ``workspace_id`` (matching the
  existing 33-table pattern from migration 0063).
- ``billing_accounts`` — one row per ``Organization``; tracks plan
  tier + seat limit + Stripe customer id + trial bookkeeping.
- ``seat_grants`` — one row per (BillingAccount, User) tuple; seat
  ledger for the future Stripe webhook integration.
- ``idp_connections`` — per-org IdP configuration (Google Workspace,
  AWS IAM Identity Center, Okta, etc.) generalising beyond
  ``EntraTenantLink``.
- ``idp_group_mappings`` — external IdP group → AQP role + scope.
- ``organizations.broker_credential_backend`` — per-org backend
  selector consumed by ``BrokerCredentialStore``.

AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0065_broker_credentials_b2b"
down_revision = "0064_schema_per_tenant_bootstrap"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # organizations.broker_credential_backend
    # ------------------------------------------------------------------
    op.add_column(
        "organizations",
        sa.Column(
            "broker_credential_backend",
            sa.String(32),
            nullable=True,
            server_default="local",
        ),
    )
    op.create_index(
        "ix_organizations_broker_credential_backend",
        "organizations",
        ["broker_credential_backend"],
    )

    # ------------------------------------------------------------------
    # broker_credentials
    # ------------------------------------------------------------------
    op.create_table(
        "broker_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column(
            "credential_kind",
            sa.String(32),
            nullable=False,
            server_default="api_key",
        ),
        sa.Column(
            "environment",
            sa.String(32),
            nullable=False,
            server_default="paper",
        ),
        sa.Column("ciphertext", sa.LargeBinary, nullable=False),
        sa.Column("nonce", sa.LargeBinary, nullable=False),
        sa.Column("wrapped_dek", sa.LargeBinary, nullable=False),
        sa.Column("kek_id", sa.String(255), nullable=False),
        sa.Column("meta", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("last_used_at", sa.DateTime, nullable=True),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
        sa.Column(
            "revoked_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
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
        sa.UniqueConstraint(
            "owner_user_id", "provider", "label", name="uq_broker_credentials"
        ),
    )
    op.create_index(
        "ix_broker_credentials_owner_active",
        "broker_credentials",
        ["owner_user_id", "is_active"],
    )
    op.create_index(
        "ix_broker_credentials_provider_workspace",
        "broker_credentials",
        ["provider", "workspace_id"],
    )
    op.create_index(
        "ix_broker_credentials_organization_id",
        "broker_credentials",
        ["organization_id"],
    )
    op.create_index(
        "ix_broker_credentials_environment",
        "broker_credentials",
        ["environment"],
    )

    # ------------------------------------------------------------------
    # billing_accounts
    # ------------------------------------------------------------------
    op.create_table(
        "billing_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "plan_tier",
            sa.String(32),
            nullable=False,
            server_default="trial",
        ),
        sa.Column("seat_limit", sa.Integer, nullable=False, server_default="5"),
        sa.Column("stripe_customer_id", sa.String(120), nullable=True, unique=True),
        sa.Column("billing_email", sa.String(320), nullable=True),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="trialing",
        ),
        sa.Column("trial_ends_at", sa.DateTime, nullable=True),
        sa.Column("suspended_at", sa.DateTime, nullable=True),
        sa.Column("suspended_reason", sa.String(255), nullable=True),
        sa.Column("meta", sa.JSON, nullable=False, server_default="{}"),
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
        "ix_billing_accounts_plan_tier", "billing_accounts", ["plan_tier"]
    )
    op.create_index(
        "ix_billing_accounts_status", "billing_accounts", ["status"]
    )

    # ------------------------------------------------------------------
    # seat_grants
    # ------------------------------------------------------------------
    op.create_table(
        "seat_grants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "billing_account_id",
            sa.String(36),
            sa.ForeignKey("billing_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(64),
            nullable=False,
            server_default="member",
        ),
        sa.Column(
            "granted_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "granted_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
        sa.Column(
            "revoked_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("meta", sa.JSON, nullable=False, server_default="{}"),
        sa.UniqueConstraint(
            "billing_account_id",
            "user_id",
            "is_active",
            name="uq_seat_grants_active",
        ),
    )
    op.create_index(
        "ix_seat_grants_billing_active",
        "seat_grants",
        ["billing_account_id", "is_active"],
    )
    op.create_index("ix_seat_grants_billing_account_id", "seat_grants", ["billing_account_id"])
    op.create_index("ix_seat_grants_user_id", "seat_grants", ["user_id"])

    # ------------------------------------------------------------------
    # idp_connections
    # ------------------------------------------------------------------
    op.create_table(
        "idp_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("connection_kind", sa.String(64), nullable=False),
        sa.Column("auth0_connection_id", sa.String(120), nullable=True),
        sa.Column("display_name", sa.String(240), nullable=True),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("allowed_email_domains", sa.Text, nullable=True),
        sa.Column("config", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("meta", sa.JSON, nullable=False, server_default="{}"),
        sa.Column(
            "created_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
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
        sa.UniqueConstraint(
            "organization_id",
            "connection_kind",
            "auth0_connection_id",
            name="uq_idp_connections_org_kind",
        ),
    )
    op.create_index(
        "ix_idp_connections_organization_id", "idp_connections", ["organization_id"]
    )
    op.create_index(
        "ix_idp_connections_connection_kind", "idp_connections", ["connection_kind"]
    )
    op.create_index(
        "ix_idp_connections_status", "idp_connections", ["status"]
    )
    op.create_index(
        "ix_idp_connections_auth0_connection_id",
        "idp_connections",
        ["auth0_connection_id"],
    )

    # ------------------------------------------------------------------
    # idp_group_mappings
    # ------------------------------------------------------------------
    op.create_table(
        "idp_group_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "idp_connection_id",
            sa.String(36),
            sa.ForeignKey("idp_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_group_name", sa.String(255), nullable=False),
        sa.Column("aqp_role", sa.String(64), nullable=False),
        sa.Column("scope_kind", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.String(36), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
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
        sa.UniqueConstraint(
            "idp_connection_id",
            "external_group_name",
            "scope_kind",
            "scope_id",
            "aqp_role",
            name="uq_idp_group_mappings_unique",
        ),
    )
    op.create_index(
        "ix_idp_group_mappings_org_active",
        "idp_group_mappings",
        ["organization_id", "is_active"],
    )
    op.create_index(
        "ix_idp_group_mappings_organization_id",
        "idp_group_mappings",
        ["organization_id"],
    )
    op.create_index(
        "ix_idp_group_mappings_idp_connection_id",
        "idp_group_mappings",
        ["idp_connection_id"],
    )

    # ------------------------------------------------------------------
    # RLS for broker_credentials — Postgres only
    # ------------------------------------------------------------------
    if not _is_postgres():
        return

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
                ALTER TABLE broker_credentials ENABLE ROW LEVEL SECURITY;
                ALTER TABLE broker_credentials FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS tenant_isolation_broker_credentials ON broker_credentials;
                CREATE POLICY tenant_isolation_broker_credentials ON broker_credentials
                    USING (workspace_id IS NULL OR workspace_id =
                           current_setting('app.current_workspace_id', true));
                GRANT SELECT, INSERT, UPDATE, DELETE ON broker_credentials TO app_runtime;
            ELSE
                RAISE NOTICE 'skipping broker_credentials RLS — app_runtime role missing';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    if _is_postgres():
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'broker_credentials'
                ) THEN
                    DROP POLICY IF EXISTS tenant_isolation_broker_credentials ON broker_credentials;
                    ALTER TABLE broker_credentials NO FORCE ROW LEVEL SECURITY;
                    ALTER TABLE broker_credentials DISABLE ROW LEVEL SECURITY;
                END IF;
            END
            $$;
            """
        )
    op.drop_index("ix_idp_group_mappings_idp_connection_id", table_name="idp_group_mappings")
    op.drop_index("ix_idp_group_mappings_organization_id", table_name="idp_group_mappings")
    op.drop_index("ix_idp_group_mappings_org_active", table_name="idp_group_mappings")
    op.drop_table("idp_group_mappings")
    op.drop_index("ix_idp_connections_auth0_connection_id", table_name="idp_connections")
    op.drop_index("ix_idp_connections_status", table_name="idp_connections")
    op.drop_index("ix_idp_connections_connection_kind", table_name="idp_connections")
    op.drop_index("ix_idp_connections_organization_id", table_name="idp_connections")
    op.drop_table("idp_connections")
    op.drop_index("ix_seat_grants_user_id", table_name="seat_grants")
    op.drop_index("ix_seat_grants_billing_account_id", table_name="seat_grants")
    op.drop_index("ix_seat_grants_billing_active", table_name="seat_grants")
    op.drop_table("seat_grants")
    op.drop_index("ix_billing_accounts_status", table_name="billing_accounts")
    op.drop_index("ix_billing_accounts_plan_tier", table_name="billing_accounts")
    op.drop_table("billing_accounts")
    op.drop_index("ix_broker_credentials_environment", table_name="broker_credentials")
    op.drop_index("ix_broker_credentials_organization_id", table_name="broker_credentials")
    op.drop_index("ix_broker_credentials_provider_workspace", table_name="broker_credentials")
    op.drop_index("ix_broker_credentials_owner_active", table_name="broker_credentials")
    op.drop_table("broker_credentials")
    op.drop_index(
        "ix_organizations_broker_credential_backend", table_name="organizations"
    )
    op.drop_column("organizations", "broker_credential_backend")
