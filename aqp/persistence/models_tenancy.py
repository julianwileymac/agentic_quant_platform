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
    """

    __tablename__ = "organizations"
    id = Column(String(36), primary_key=True, default=_uuid)
    slug = Column(String(80), nullable=False, unique=True, index=True)
    name = Column(String(240), nullable=False)
    billing_email = Column(String(320), nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    meta = Column(JSON, default=dict)
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


__all__ = [
    "ConfigOverlayRow",
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
