"""Seed the canonical ``Wiley Tech`` organization + ``Julian`` user.

Revision ID: 0051_seed_wiley_tech
Revises: 0050_terraform_iac_plus_entra
Create Date: 2026-05-17

Idempotent seed + legacy-row re-stamp migration:

1. Upserts organization ``(slug=wiley-tech, name="Wiley Tech")`` with
   a deterministic UUID derived via ``uuid5(NAMESPACE_DNS, ...)``.
2. Upserts team ``(slug=core)`` under it.
3. Upserts workspace / project / lab rows.
4. Upserts user ``(email=julian@wiley.tech, display_name="Julian",
   auth_provider="msal_entra")`` with deterministic UUID.
5. Upserts 5 owner :class:`Membership` rows (org / team / workspace /
   project / lab) with ``live_control=True``.
6. **Re-stamps every legacy row** that currently points at the
   ``default-*`` seed (from migration 0017) to point at the Wiley
   Tech seed instead. The default-* rows are preserved so legacy
   foreign-key chains remain valid; new resources land in Wiley
   Tech going forward.
7. Seeds default :class:`TerraformProvider` rows (local + docker +
   baremetal + rpi_cluster + hcp + the matching cloud kind from
   ``AQP_DEFAULT_CLOUD_PROVIDER``).
8. Seeds an :class:`EntraTenantLink` for ``AQP_AZURE_TENANT_ID``
   when it is set; otherwise the link is created later via the
   onboarding wizard.

AGENTS rule 6: this migration is **immutable** once shipped.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op


logger = logging.getLogger(__name__)


revision = "0051_seed_wiley_tech"
down_revision = "0050_terraform_iac_plus_entra"
branch_labels = None
depends_on = None


# --- Legacy seed IDs (mirrored from aqp.config.defaults to keep the
# migration self-contained per the 0021 pattern). --------------------
DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_TEAM_ID = "00000000-0000-0000-0000-000000000002"
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000003"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000004"
DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000005"
DEFAULT_LAB_ID = "00000000-0000-0000-0000-000000000006"


# --- Wiley Tech deterministic seed IDs ------------------------------
# uuid5(NAMESPACE_DNS, "<scope>.wiley-tech.aqp") so the seed is
# bit-for-bit reproducible across clusters.
_NAMESPACE = uuid.NAMESPACE_DNS


def _seed_id(scope: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{scope}.wiley-tech.aqp"))


WILEY_TECH_ORG_ID = _seed_id("org")
WILEY_TECH_TEAM_ID = _seed_id("team")
WILEY_TECH_USER_ID = _seed_id("user")
WILEY_TECH_WORKSPACE_ID = _seed_id("workspace")
WILEY_TECH_PROJECT_ID = _seed_id("project")
WILEY_TECH_LAB_ID = _seed_id("lab")


def _wiley_membership_id(scope_kind: str) -> str:
    return _seed_id(f"membership.{scope_kind}")


# Existing tenancy-scoped tables that point at the legacy default-org
# / default-workspace / default-project / default-user. The seed
# re-points every legacy row to the Wiley Tech IDs. Each tuple is
# ``(table_name, list_of_legacy_column_pairs)``.
# Format per pair: (column_name, legacy_id, new_id, column_is_required)
_LEGACY_STAMP_TABLES: tuple[tuple[str, str, str, str], ...] = (
    # (table_name, column_name, legacy_id, new_id)
    ("strategies", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("strategies", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("strategies", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("backtest_runs", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("backtest_runs", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("backtest_runs", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("paper_trading_runs", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("paper_trading_runs", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("paper_trading_runs", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("dataset_catalogs", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("dataset_catalogs", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("dataset_catalogs", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("dataset_versions", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("dataset_versions", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("dataset_versions", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("model_deployments", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("model_deployments", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("model_deployments", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("bots", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("bots", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("bots", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("bot_versions", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("bot_versions", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("bot_versions", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("bot_deployments", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("bot_deployments", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("bot_deployments", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("agent_runs", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("agent_runs", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("agent_runs", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("agent_runs_v2", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("agent_runs_v2", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("agent_runs_v2", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("agent_spec_versions", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("agent_spec_versions", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("agent_spec_versions", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("rl_runs", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("rl_runs", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("rl_runs", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("rl_experiment_versions", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("rl_experiment_versions", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("rl_experiment_versions", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("analysis_runs", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("analysis_runs", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("analysis_runs", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("analysis_spec_versions", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("analysis_spec_versions", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("analysis_spec_versions", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("workflow_runs", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("workflow_runs", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("workflow_runs", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("aqp_experiments", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("aqp_experiments", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("aqp_experiments", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("aqp_tests", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("aqp_tests", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("aqp_tests", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("resources", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("resources", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("resources", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("ml_alpha_backtest_runs", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("ml_alpha_backtest_runs", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("ml_alpha_backtest_runs", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
    ("ml_experiment_runs", "owner_user_id", DEFAULT_USER_ID, WILEY_TECH_USER_ID),
    ("ml_experiment_runs", "workspace_id", DEFAULT_WORKSPACE_ID, WILEY_TECH_WORKSPACE_ID),
    ("ml_experiment_runs", "project_id", DEFAULT_PROJECT_ID, WILEY_TECH_PROJECT_ID),
)


def _table_exists(bind, table_name: str) -> bool:
    """Return True iff the dialect knows about ``table_name``."""
    try:
        inspector = sa.inspect(bind)
        return table_name in inspector.get_table_names()
    except Exception:  # pragma: no cover - dialect quirks
        return False


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    try:
        inspector = sa.inspect(bind)
        cols = {c["name"] for c in inspector.get_columns(table_name)}
        return column_name in cols
    except Exception:  # pragma: no cover
        return False


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    now = datetime.utcnow()
    empty_json = "{}"

    _seed_organization(bind, dialect, now, empty_json)
    _seed_team(bind, dialect, now, empty_json)
    _seed_workspace(bind, dialect, now, empty_json)
    _seed_project(bind, dialect, now, empty_json)
    _seed_lab(bind, dialect, now, empty_json)
    _seed_user(bind, dialect, now, empty_json)
    _seed_memberships(bind, dialect, now)
    _restamp_legacy_rows(bind, dialect)
    _seed_terraform_providers(bind, dialect, now)
    _seed_entra_tenant_link(bind, dialect, now)


def _seed_organization(bind, dialect: str, now: datetime, empty_json: str) -> None:
    name = os.environ.get("AQP_DEFAULT_ORGANIZATION_NAME", "Wiley Tech")
    slug = os.environ.get("AQP_DEFAULT_ORGANIZATION_SLUG", "wiley-tech")
    billing_email = os.environ.get("AQP_DEFAULT_ADMIN_EMAIL", "julian@wiley.tech")
    if dialect == "postgresql":
        bind.execute(
            sa.text(
                """
                INSERT INTO organizations (
                    id, slug, name, billing_email, status, meta, created_at, updated_at
                ) VALUES (
                    :id, :slug, :name, :billing_email, 'active', :meta, :now, :now
                )
                ON CONFLICT (id) DO UPDATE SET
                    slug = EXCLUDED.slug,
                    name = EXCLUDED.name,
                    billing_email = EXCLUDED.billing_email,
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "id": WILEY_TECH_ORG_ID,
                "slug": slug,
                "name": name,
                "billing_email": billing_email,
                "meta": empty_json,
                "now": now,
            },
        )
    else:
        _sqlite_upsert(
            bind,
            "organizations",
            "id",
            {
                "id": WILEY_TECH_ORG_ID,
                "slug": slug,
                "name": name,
                "billing_email": billing_email,
                "status": "active",
                "meta": empty_json,
                "created_at": now,
                "updated_at": now,
            },
        )


def _seed_team(bind, dialect: str, now: datetime, empty_json: str) -> None:
    row = {
        "id": WILEY_TECH_TEAM_ID,
        "org_id": WILEY_TECH_ORG_ID,
        "slug": "core",
        "name": "Core",
        "description": "Default team for Wiley Tech members.",
        "meta": empty_json,
        "created_at": now,
        "updated_at": now,
    }
    if dialect == "postgresql":
        bind.execute(
            sa.text(
                """
                INSERT INTO teams (
                    id, org_id, slug, name, description, meta, created_at, updated_at
                ) VALUES (
                    :id, :org_id, :slug, :name, :description, :meta, :now, :now
                )
                ON CONFLICT (id) DO UPDATE SET
                    org_id = EXCLUDED.org_id,
                    slug = EXCLUDED.slug,
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {**row, "now": now},
        )
    else:
        _sqlite_upsert(bind, "teams", "id", row)


def _seed_workspace(bind, dialect: str, now: datetime, empty_json: str) -> None:
    row = {
        "id": WILEY_TECH_WORKSPACE_ID,
        "org_id": WILEY_TECH_ORG_ID,
        "slug": "main",
        "name": "Main Workspace",
        "description": "Default workspace for Wiley Tech resources.",
        "visibility": "org",
        "archived": False,
        "settings": empty_json,
        "meta": empty_json,
        "created_at": now,
        "updated_at": now,
    }
    if dialect == "postgresql":
        bind.execute(
            sa.text(
                """
                INSERT INTO workspaces (
                    id, org_id, slug, name, description, visibility,
                    archived, settings, meta, created_at, updated_at
                ) VALUES (
                    :id, :org_id, :slug, :name, :description, :visibility,
                    false, :settings, :meta, :now, :now
                )
                ON CONFLICT (id) DO UPDATE SET
                    org_id = EXCLUDED.org_id,
                    slug = EXCLUDED.slug,
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    visibility = EXCLUDED.visibility,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {**row, "now": now},
        )
    else:
        _sqlite_upsert(bind, "workspaces", "id", row)


def _seed_project(bind, dialect: str, now: datetime, empty_json: str) -> None:
    row = {
        "id": WILEY_TECH_PROJECT_ID,
        "workspace_id": WILEY_TECH_WORKSPACE_ID,
        "slug": "main",
        "name": "Main Project",
        "description": "Default project for Wiley Tech strategies and bots.",
        "archived": False,
        "settings": empty_json,
        "meta": empty_json,
        "created_at": now,
        "updated_at": now,
    }
    if dialect == "postgresql":
        bind.execute(
            sa.text(
                """
                INSERT INTO projects (
                    id, workspace_id, slug, name, description,
                    archived, settings, meta, created_at, updated_at
                ) VALUES (
                    :id, :workspace_id, :slug, :name, :description,
                    false, :settings, :meta, :now, :now
                )
                ON CONFLICT (id) DO UPDATE SET
                    workspace_id = EXCLUDED.workspace_id,
                    slug = EXCLUDED.slug,
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {**row, "now": now},
        )
    else:
        _sqlite_upsert(bind, "projects", "id", row)


def _seed_lab(bind, dialect: str, now: datetime, empty_json: str) -> None:
    row = {
        "id": WILEY_TECH_LAB_ID,
        "workspace_id": WILEY_TECH_WORKSPACE_ID,
        "slug": "main",
        "name": "Main Lab",
        "description": "Default research lab for Wiley Tech notebooks.",
        "kernel_image": None,
        "archived": False,
        "last_active_at": None,
        "settings": empty_json,
        "meta": empty_json,
        "created_at": now,
        "updated_at": now,
    }
    if dialect == "postgresql":
        bind.execute(
            sa.text(
                """
                INSERT INTO labs (
                    id, workspace_id, slug, name, description,
                    kernel_image, archived, last_active_at, settings, meta,
                    created_at, updated_at
                ) VALUES (
                    :id, :workspace_id, :slug, :name, :description,
                    :kernel_image, false, :last_active_at, :settings, :meta,
                    :now, :now
                )
                ON CONFLICT (id) DO UPDATE SET
                    workspace_id = EXCLUDED.workspace_id,
                    slug = EXCLUDED.slug,
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {**row, "now": now},
        )
    else:
        _sqlite_upsert(bind, "labs", "id", row)


def _seed_user(bind, dialect: str, now: datetime, empty_json: str) -> None:
    email = os.environ.get("AQP_DEFAULT_ADMIN_EMAIL", "julian@wiley.tech")
    display_name = os.environ.get("AQP_DEFAULT_ADMIN_DISPLAY_NAME", "Julian")
    # auth_subject is "msal_entra|<oid>" once the matching Entra user
    # signs in. Until then we stamp a placeholder unique to the seed so
    # the column's unique constraint doesn't bite.
    auth_subject = f"seed:wiley-tech:{WILEY_TECH_USER_ID}"
    row = {
        "id": WILEY_TECH_USER_ID,
        "email": email,
        "display_name": display_name,
        "auth_subject": auth_subject,
        "auth_provider": "msal_entra",
        "status": "active",
        "avatar_url": None,
        "meta": json.dumps(
            {
                "seeded_by": "alembic:0051_seed_wiley_tech",
                "rebind_on_first_msal_login": True,
            }
        ),
        "last_login_at": None,
        "created_at": now,
        "updated_at": now,
    }
    if dialect == "postgresql":
        bind.execute(
            sa.text(
                """
                INSERT INTO users (
                    id, email, display_name, auth_subject, auth_provider,
                    status, avatar_url, meta, last_login_at, created_at, updated_at
                ) VALUES (
                    :id, :email, :display_name, :auth_subject, :auth_provider,
                    :status, :avatar_url, :meta, :last_login_at, :now, :now
                )
                ON CONFLICT (id) DO UPDATE SET
                    email = EXCLUDED.email,
                    display_name = EXCLUDED.display_name,
                    auth_provider = EXCLUDED.auth_provider,
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {**row, "now": now},
        )
    else:
        _sqlite_upsert(bind, "users", "id", row)


def _seed_memberships(bind, dialect: str, now: datetime) -> None:
    pairs = (
        ("org", WILEY_TECH_ORG_ID),
        ("team", WILEY_TECH_TEAM_ID),
        ("workspace", WILEY_TECH_WORKSPACE_ID),
        ("project", WILEY_TECH_PROJECT_ID),
        ("lab", WILEY_TECH_LAB_ID),
    )
    for scope_kind, scope_id in pairs:
        row = {
            "id": _wiley_membership_id(scope_kind),
            "user_id": WILEY_TECH_USER_ID,
            "scope_kind": scope_kind,
            "scope_id": scope_id,
            "role": "owner",
            "live_control": True,
            "granted_by": WILEY_TECH_USER_ID,
            "granted_at": now,
            "expires_at": None,
            "meta": "{}",
        }
        if dialect == "postgresql":
            bind.execute(
                sa.text(
                    """
                    INSERT INTO memberships (
                        id, user_id, scope_kind, scope_id, role,
                        live_control, granted_by, granted_at, expires_at, meta
                    ) VALUES (
                        :id, :user_id, :scope_kind, :scope_id, :role,
                        :live_control, :granted_by, :granted_at, :expires_at, :meta
                    )
                    ON CONFLICT ON CONSTRAINT uq_memberships_user_scope_role
                    DO UPDATE SET
                        live_control = EXCLUDED.live_control,
                        granted_by = EXCLUDED.granted_by
                    """
                ),
                row,
            )
        else:
            _sqlite_upsert(bind, "memberships", "id", row)


def _restamp_legacy_rows(bind, dialect: str) -> None:
    """Re-point every legacy-default-* tenancy reference to Wiley Tech.

    Rows that already point at non-default tenancies are left alone.
    Tables / columns that don't exist in the current schema are
    skipped (idempotent across partial-rollback states).
    """
    seen: set[tuple[str, str]] = set()
    for table, column, legacy_id, new_id in _LEGACY_STAMP_TABLES:
        if (table, column) in seen:
            continue
        seen.add((table, column))
        if not _table_exists(bind, table):
            logger.info("0051 skip restamp: table %s missing", table)
            continue
        if not _column_exists(bind, table, column):
            logger.info("0051 skip restamp: column %s.%s missing", table, column)
            continue
        try:
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET {column} = :new_id WHERE {column} = :legacy_id"
                ),
                {"new_id": new_id, "legacy_id": legacy_id},
            )
        except Exception as exc:  # noqa: BLE001 — best-effort backfill
            logger.warning(
                "0051 restamp failed for %s.%s: %s", table, column, exc
            )


def _seed_terraform_providers(bind, dialect: str, now: datetime) -> None:
    """Seed the canonical out-of-the-box Terraform providers."""
    cloud = (os.environ.get("AQP_DEFAULT_CLOUD_PROVIDER") or "").strip().lower()
    seed_kinds = ["local", "docker", "baremetal", "rpi_cluster", "hcp"]
    if cloud in {"aws", "gcp", "azure"} and cloud not in seed_kinds:
        seed_kinds.append(cloud)
    for kind in seed_kinds:
        provider_id = _seed_id(f"terraform_provider.{kind}")
        slug = f"default-{kind}"
        name = f"Default {kind.replace('_', ' ').title()} Provider"
        row = {
            "id": provider_id,
            "slug": slug,
            "name": name,
            "kind": kind,
            "default_region": None,
            "config_json": "{}",
            "credential_key": None,
            "status": "active",
            "meta": json.dumps({"seeded_by": "alembic:0051_seed_wiley_tech"}),
            "created_at": now,
            "updated_at": now,
            "owner_user_id": WILEY_TECH_USER_ID,
            "workspace_id": WILEY_TECH_WORKSPACE_ID,
        }
        if dialect == "postgresql":
            bind.execute(
                sa.text(
                    """
                    INSERT INTO terraform_providers (
                        id, slug, name, kind, default_region, config_json,
                        credential_key, status, meta, created_at, updated_at,
                        owner_user_id, workspace_id
                    ) VALUES (
                        :id, :slug, :name, :kind, :default_region, :config_json,
                        :credential_key, :status, :meta, :created_at, :updated_at,
                        :owner_user_id, :workspace_id
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        slug = EXCLUDED.slug,
                        name = EXCLUDED.name,
                        kind = EXCLUDED.kind,
                        status = EXCLUDED.status,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                row,
            )
        else:
            _sqlite_upsert(bind, "terraform_providers", "id", row)


def _seed_entra_tenant_link(bind, dialect: str, now: datetime) -> None:
    """When ``AQP_AZURE_TENANT_ID`` is set, link it to Wiley Tech."""
    entra_tid = (os.environ.get("AQP_AZURE_TENANT_ID") or os.environ.get("AQP_MSAL_TENANT_ID") or "").strip()
    if not entra_tid:
        logger.info(
            "0051: AQP_AZURE_TENANT_ID / AQP_MSAL_TENANT_ID not set; "
            "EntraTenantLink left empty (admin can link via the onboarding wizard)."
        )
        return
    link_id = _seed_id(f"entra_tenant_link.{entra_tid}")
    primary_domain = (os.environ.get("AQP_MSAL_PRIMARY_DOMAIN") or "wiley.tech").strip()
    row = {
        "id": link_id,
        "organization_id": WILEY_TECH_ORG_ID,
        "entra_tenant_id": entra_tid,
        "primary_domain": primary_domain,
        "display_name": "Wiley Tech (Entra ID)",
        "status": "active",
        "allowed_email_domains": primary_domain,
        "role_mapping": "{}",
        "requested_by_email": None,
        "approved_by_user_id": None,
        "approved_at": now,
        "revoked_at": None,
        "meta": json.dumps({"seeded_by": "alembic:0051_seed_wiley_tech"}),
        "created_at": now,
        "updated_at": now,
    }
    if dialect == "postgresql":
        bind.execute(
            sa.text(
                """
                INSERT INTO entra_tenant_links (
                    id, organization_id, entra_tenant_id, primary_domain,
                    display_name, status, allowed_email_domains, role_mapping,
                    requested_by_email, approved_by_user_id, approved_at,
                    revoked_at, meta, created_at, updated_at
                ) VALUES (
                    :id, :organization_id, :entra_tenant_id, :primary_domain,
                    :display_name, :status, :allowed_email_domains, :role_mapping,
                    :requested_by_email, :approved_by_user_id, :approved_at,
                    :revoked_at, :meta, :created_at, :updated_at
                )
                ON CONFLICT (entra_tenant_id) DO UPDATE SET
                    organization_id = EXCLUDED.organization_id,
                    primary_domain = EXCLUDED.primary_domain,
                    display_name = EXCLUDED.display_name,
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            row,
        )
    else:
        _sqlite_upsert(bind, "entra_tenant_links", "id", row)


def _sqlite_upsert(bind, table: str, pk: str, row: dict) -> None:
    """Best-effort INSERT-OR-REPLACE for the SQLite test path.

    We use a simple ``DELETE + INSERT`` because SQLite's ``ON CONFLICT
    DO UPDATE`` requires explicit conflict targets that some legacy
    test fixtures don't declare. Idempotent because the new row
    carries the deterministic PK.
    """
    columns = list(row.keys())
    placeholders = ", ".join(f":{c}" for c in columns)
    bind.execute(sa.text(f"DELETE FROM {table} WHERE {pk} = :pk"), {"pk": row[pk]})
    bind.execute(
        sa.text(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"),
        row,
    )


def downgrade() -> None:
    """Irreversible: the legacy-row restamp is intentionally one-way.

    Removing the Wiley Tech seed rows after legacy rows have been
    re-pointed would orphan them. Operators wanting a clean rollback
    should restore a pre-0051 database snapshot.
    """
    return None
