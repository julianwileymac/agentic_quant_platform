"""Multi-tenant identity tables: Org > Team > User > Workspace > Project / Lab.

Borrowed shape:

- Lean's :class:`Project` / :class:`Collaborator` (``OwnerId``,
  ``OrganizationId``, ``Permission``, ``Owner``, ``LiveControl``) — see
  ``inspiration/Lean-master/Common/Api/Project.cs``. We collapse the per-
  scope collaborator list into a single polymorphic :class:`Membership`
  table keyed by ``(scope_kind, scope_id)``.
- vectorbt-pro's settings-as-overlay model — :class:`ConfigOverlayRow`
  stores one JSON payload per ``(scope_kind, scope_id, namespace)`` and
  is merged into the effective config by :func:`aqp.config.resolve_config`.

The ``aqp/auth/context.py::RequestContext`` mirrors Lean's
``AlgorithmNodePacket``: every code path that runs on a user's behalf
carries ``(user_id, org_id, team_id, workspace_id, project_id, lab_id,
run_id)`` so the chokepoints in ``aqp/persistence/ledger.py``,
``aqp/agents/runtime.py``, ``aqp/rag/hierarchy.py``, and
``aqp/data/iceberg_catalog.py`` can stamp ownership consistently.

Notes on scope_id / FK enforcement:

The :class:`Membership` and :class:`ConfigOverlayRow` rows store a
free-form ``scope_id`` because they participate in five different
scope_kinds (``org``, ``team``, ``user``, ``workspace``, ``project``,
``lab``). Application code is responsible for keeping these in sync —
the API layer in ``aqp/api/routes/users.py`` and the admin pages clean
up child memberships when a parent scope is deleted.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from aqp.persistence._tenancy_mixins import (
    LabScopedMixin,
    ProjectScopedMixin,
    TenantOwnedMixin,
)
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Organization(Base):
    """Top of the tenancy hierarchy. Owns teams and workspaces.

    A single AQP deployment can host multiple organizations; the local-first
    seed (`default-org`) is created by :ref:`migration 0017 <alembic-0017>`
    and is the home for every legacy resource backfilled by 0018.

    Workstream F.1 adds three tenancy-strategy columns:

    - ``tenancy_strategy`` — the active isolation kind
      (``shared_schema_rls`` / ``schema_per_tenant`` /
      ``database_per_enterprise``). Read by
      :class:`HybridStrategy` per session checkout.
    - ``tenancy_schema_name`` — populated by
      :class:`SchemaPerTenantStrategy.onboard` so a re-onboard or a
      diagnostic UI can show the canonical schema name without
      re-deriving it.
    - ``tenancy_dsn_vault_path`` — populated by
      :class:`DatabasePerEnterpriseStrategy.onboard` so an operator can
      audit which Vault path holds the dedicated DSN.
    """

    __tablename__ = "organizations"
    id = Column(String(36), primary_key=True, default=_uuid)
    slug = Column(String(80), nullable=False, unique=True, index=True)
    name = Column(String(240), nullable=False)
    billing_email = Column(String(320), nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    meta = Column(JSON, default=dict)
    tenancy_strategy = Column(
        String(32), nullable=True, index=True, default="shared_schema_rls"
    )
    tenancy_schema_name = Column(String(80), nullable=True)
    tenancy_dsn_vault_path = Column(String(240), nullable=True)
    # AGENTS rule 55 — selects the backend BrokerCredentialStore
    # dispatches to for this org. ``local`` = Postgres ``broker_credentials``
    # table (B2C / trial / Pro tiers); ``hashicorp_vault`` / ``aws_sm`` /
    # ``azure_kv`` / ``gcp_sm`` = enterprise tenant's external KMS.
    broker_credential_backend = Column(
        String(32), nullable=True, index=True, default="local"
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    teams = relationship("Team", back_populates="organization", cascade="all,delete-orphan")
    workspaces = relationship(
        "Workspace", back_populates="organization", cascade="all,delete-orphan"
    )


class Team(Base):
    """A subgroup within an :class:`Organization`. Users belong to teams via
    :class:`Membership` rows; teams can in turn be members of workspaces."""

    __tablename__ = "teams"
    id = Column(String(36), primary_key=True, default=_uuid)
    org_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slug = Column(String(80), nullable=False)
    name = Column(String(240), nullable=False)
    description = Column(Text, nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    organization = relationship("Organization", back_populates="teams")

    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_teams_org_slug"),
    )


class User(Base):
    """An authenticated identity. ``auth_subject`` is the OIDC ``sub`` claim
    (or the local username for ``auth_provider="local"``). ``email`` is the
    canonical lookup key for invitations and notifications."""

    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=_uuid)
    email = Column(String(320), nullable=False, unique=True, index=True)
    display_name = Column(String(240), nullable=False)
    auth_subject = Column(String(240), nullable=True, unique=True, index=True)
    auth_provider = Column(String(64), nullable=False, default="local", index=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    avatar_url = Column(String(1024), nullable=True)
    meta = Column(JSON, default=dict)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    memberships = relationship(
        "Membership",
        back_populates="user",
        cascade="all,delete-orphan",
        foreign_keys="Membership.user_id",
    )


class Workspace(Base):
    """Visibility-scoped container of projects and labs.

    Visibility:

    - ``private``: only members listed on the workspace can access it.
    - ``team``: members of any team in the same org with explicit membership.
    - ``org``: every member of the parent organization can read.
    """

    __tablename__ = "workspaces"
    id = Column(String(36), primary_key=True, default=_uuid)
    org_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slug = Column(String(80), nullable=False)
    name = Column(String(240), nullable=False)
    description = Column(Text, nullable=True)
    visibility = Column(String(32), nullable=False, default="team", index=True)
    archived = Column(Boolean, nullable=False, default=False, index=True)
    settings = Column(JSON, default=dict)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    organization = relationship("Organization", back_populates="workspaces")
    projects = relationship(
        "Project", back_populates="workspace", cascade="all,delete-orphan"
    )
    labs = relationship("Lab", back_populates="workspace", cascade="all,delete-orphan")

    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_workspaces_org_slug"),
    )


class Project(Base):
    """The trading-bot artifact: strategies, backtests, agents, deployments
    are all owned (transitively) by a :class:`Project`. Compare to Lean's
    ``Project`` (algorithm + collaborators + libraries)."""

    __tablename__ = "projects"
    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slug = Column(String(80), nullable=False)
    name = Column(String(240), nullable=False)
    description = Column(Text, nullable=True)
    archived = Column(Boolean, nullable=False, default=False, index=True)
    settings = Column(JSON, default=dict)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    workspace = relationship("Workspace", back_populates="projects")

    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_projects_workspace_slug"),
    )


class Lab(Base):
    """The interactive-research artifact: notebook sessions, RAG corpora,
    memory episodes accumulate inside a Lab. Lean folds notebooks into the
    same ``Project`` via :class:`AlgorithmMode.Research`; we keep them
    separate so the UI can show distinct surfaces."""

    __tablename__ = "labs"
    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slug = Column(String(80), nullable=False)
    name = Column(String(240), nullable=False)
    description = Column(Text, nullable=True)
    kernel_image = Column(String(240), nullable=True)
    archived = Column(Boolean, nullable=False, default=False, index=True)
    last_active_at = Column(DateTime, nullable=True)
    settings = Column(JSON, default=dict)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    workspace = relationship("Workspace", back_populates="labs")

    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_labs_workspace_slug"),
    )


class Membership(Base):
    """One ``(user, scope, role)`` grant. Polymorphic over scope_kind:

    - ``org``: scope_id is an Organization id
    - ``team``: scope_id is a Team id
    - ``workspace``: scope_id is a Workspace id
    - ``project``: scope_id is a Project id
    - ``lab``: scope_id is a Lab id

    The role lattice is ``viewer < editor < admin < owner``. ``live_control``
    is a Lean-style boolean: a user with project ``editor`` can still be
    barred from triggering live trading by withholding live_control.
    """

    __tablename__ = "memberships"
    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_kind = Column(String(32), nullable=False, index=True)
    scope_id = Column(String(36), nullable=False, index=True)
    role = Column(String(32), nullable=False, default="viewer", index=True)
    live_control = Column(Boolean, nullable=False, default=False)
    granted_by = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    granted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    meta = Column(JSON, default=dict)

    user = relationship("User", back_populates="memberships", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint(
            "user_id", "scope_kind", "scope_id", "role",
            name="uq_memberships_user_scope_role",
        ),
        Index("ix_memberships_scope", "scope_kind", "scope_id"),
    )


class ConfigOverlayRow(Base):
    """One overlay layer in the global > org > team > user > workspace >
    project > lab config stack. Resolved by
    :func:`aqp.config.resolve_config` using
    :func:`aqp.config.merge_dicts` semantics (recursive merge with
    :class:`AtomicDict` opt-out and ``UNSET`` removal)."""

    __tablename__ = "config_overlays"
    id = Column(String(36), primary_key=True, default=_uuid)
    scope_kind = Column(String(32), nullable=False, index=True)
    scope_id = Column(String(36), nullable=False, index=True)
    namespace = Column(String(120), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)
    updated_by = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "scope_kind", "scope_id", "namespace",
            name="uq_config_overlays_scope_namespace",
        ),
        Index("ix_config_overlays_scope", "scope_kind", "scope_id"),
    )


# ---------------------------------------------------------------------------
# Phase 5 — Per-org IdP connection records + external-group → AQP-role
# mapping. Generalises beyond the existing ``EntraTenantLink`` (which is
# Azure AD-specific) so each org can attach Google Workspace, AWS IAM
# Identity Center, Okta, OneLogin, JumpCloud, or a generic SAML/OIDC
# connection on top.
# ---------------------------------------------------------------------------


class IdpConnectionRecord(Base):
    """Per-organization IdP connection configuration.

    ``EntraTenantLink`` remains the canonical record for Azure AD-only
    deployments (it carries the pending/active promotion lifecycle).
    This table is the generalisation for the additional connection
    kinds — one row per (organization, kind) tuple, with the
    Auth0-side connection id (or vendor-native equivalent) recorded so
    the admin UI can show "the GitHub Enterprise SSO config for Acme".

    The ``config`` JSON blob carries connection-specific non-secret
    fields (Workforce pool id, allowed email domains, default role,
    etc.). Secret material (client secrets, signing certs) NEVER lives
    here — it resolves via :class:`aqp.credentials.CredentialResolver`
    under ``CredentialKey(f"idp:{connection_kind}:{org_id}", "client")``.
    """

    __tablename__ = "idp_connections"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connection_kind = Column(String(64), nullable=False, index=True)
    auth0_connection_id = Column(String(120), nullable=True, index=True)
    display_name = Column(String(240), nullable=True)
    # "pending" — admin created the row but hasn't pushed to Auth0 yet.
    # "active" — fully provisioned; users can sign in via this connection.
    # "suspended" — temporarily disabled (e.g. license expired upstream).
    # "revoked" — permanently torn down; kept for audit history.
    status = Column(String(32), nullable=False, default="pending", index=True)
    # Allowed email domains as a CSV. Empty means "any email accepted
    # by the IdP". Operators usually pin to their owned domains to
    # mitigate the JIT-on-unknown-domain attack vector.
    allowed_email_domains = Column(Text, nullable=True)
    config = Column(JSON, default=dict)
    meta = Column(JSON, default=dict)
    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "connection_kind", "auth0_connection_id",
            name="uq_idp_connections_org_kind",
        ),
    )


# Canonical connection-kind discriminators recognised by the platform.
IDP_CONNECTION_ENTRA: str = "entra"
IDP_CONNECTION_GOOGLE_WORKSPACE: str = "google_workspace"
IDP_CONNECTION_AWS_IAM_IDENTITY_CENTER: str = "aws_iam_identity_center"
IDP_CONNECTION_OKTA: str = "okta"
IDP_CONNECTION_ONELOGIN: str = "onelogin"
IDP_CONNECTION_JUMPCLOUD: str = "jumpcloud"
IDP_CONNECTION_GENERIC_OIDC: str = "generic_oidc"
IDP_CONNECTION_GENERIC_SAML: str = "generic_saml"

IDP_CONNECTION_KINDS: frozenset[str] = frozenset(
    {
        IDP_CONNECTION_ENTRA,
        IDP_CONNECTION_GOOGLE_WORKSPACE,
        IDP_CONNECTION_AWS_IAM_IDENTITY_CENTER,
        IDP_CONNECTION_OKTA,
        IDP_CONNECTION_ONELOGIN,
        IDP_CONNECTION_JUMPCLOUD,
        IDP_CONNECTION_GENERIC_OIDC,
        IDP_CONNECTION_GENERIC_SAML,
    }
)


class IdpGroupMapping(Base):
    """External IdP group → AQP role mapping.

    Drives the post-login Action ``aqp-idp-group-sync``: when a user
    signs in through an :class:`IdpConnectionRecord`, the Action reads
    their group claim (Azure ``groups``, Google ``hd``-based group,
    Okta ``groups``, ...) and upserts :class:`Membership` rows on the
    org / team / workspace scopes listed in the mapping.

    One mapping row maps ONE external group to ONE AQP role on ONE
    scope. Operators add multiple rows for richer fan-out (e.g.
    "AQP Quants" → admin on Org X AND editor on Workspace Y).
    """

    __tablename__ = "idp_group_mappings"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    idp_connection_id = Column(
        String(36),
        ForeignKey("idp_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_group_name = Column(String(255), nullable=False)
    aqp_role = Column(String(64), nullable=False)  # viewer | editor | admin | owner
    # The scope this mapping grants on. Mirrors Membership.scope_kind /
    # Membership.scope_id (which is the polymorphic discriminator
    # explained in this module's header comment).
    scope_kind = Column(String(32), nullable=False)  # org | team | workspace | project | lab
    scope_id = Column(String(36), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "idp_connection_id",
            "external_group_name",
            "scope_kind",
            "scope_id",
            "aqp_role",
            name="uq_idp_group_mappings_unique",
        ),
        Index(
            "ix_idp_group_mappings_org_active",
            "organization_id",
            "is_active",
        ),
    )


__all__ = [
    "ConfigOverlayRow",
    "IDP_CONNECTION_AWS_IAM_IDENTITY_CENTER",
    "IDP_CONNECTION_ENTRA",
    "IDP_CONNECTION_GENERIC_OIDC",
    "IDP_CONNECTION_GENERIC_SAML",
    "IDP_CONNECTION_GOOGLE_WORKSPACE",
    "IDP_CONNECTION_JUMPCLOUD",
    "IDP_CONNECTION_KINDS",
    "IDP_CONNECTION_OKTA",
    "IDP_CONNECTION_ONELOGIN",
    "IdpConnectionRecord",
    "IdpGroupMapping",
    "Lab",
    "LabScopedMixin",
    "Membership",
    "Organization",
    "Project",
    "ProjectScopedMixin",
    "Team",
    "TenantOwnedMixin",
    "User",
    "Workspace",
]
