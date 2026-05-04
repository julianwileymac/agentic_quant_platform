"""Tenancy ownership mixins.

Lives in its own module to avoid circular imports: every ``models*.py``
file imports these, and the tenancy table definitions in
:mod:`aqp.persistence.models_tenancy` import ``Base`` from
:mod:`aqp.persistence.models`. Defining the mixins here breaks the cycle.

The mixins use SQLAlchemy's :class:`declared_attr` so the same
:class:`Column` objects can be safely re-applied to many subclasses.
``ForeignKey`` targets are referenced by table name string, so this
module does **not** need to import the tenancy classes themselves.

Three mixins cover every user-created resource:

- :class:`TenantOwnedMixin` — owner_user_id + workspace_id (required).
- :class:`ProjectScopedMixin` — adds project_id (trading-bot artifacts).
- :class:`LabScopedMixin` — adds lab_id (interactive-research artifacts).

Pick exactly one per ORM class:

.. code-block:: python

    class Strategy(Base, ProjectScopedMixin):
        ...

    class RagCorpus(Base, LabScopedMixin):
        ...

    class Session(Base, TenantOwnedMixin):
        ...
"""
from __future__ import annotations

from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import declared_attr

from aqp.config.defaults import (
    DEFAULT_LAB_ID,
    DEFAULT_PROJECT_ID,
    DEFAULT_USER_ID,
    DEFAULT_WORKSPACE_ID,
)


class TenantOwnedMixin:
    """Adds owner_user_id + workspace_id to a model."""

    @declared_attr
    def owner_user_id(cls):  # noqa: N805 - SQLA declared_attr style
        return Column(
            String(36),
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
            default=DEFAULT_USER_ID,
        )

    @declared_attr
    def workspace_id(cls):
        return Column(
            String(36),
            ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
            default=DEFAULT_WORKSPACE_ID,
        )


class ProjectScopedMixin(TenantOwnedMixin):
    """Adds project_id (FK to ``projects``) on top of the tenant baseline."""

    @declared_attr
    def project_id(cls):
        return Column(
            String(36),
            ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
            default=DEFAULT_PROJECT_ID,
        )


class LabScopedMixin(TenantOwnedMixin):
    """Adds lab_id (FK to ``labs``) on top of the tenant baseline."""

    @declared_attr
    def lab_id(cls):
        return Column(
            String(36),
            ForeignKey("labs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
            default=DEFAULT_LAB_ID,
        )


__all__ = ["LabScopedMixin", "ProjectScopedMixin", "TenantOwnedMixin"]
