"""Canonical DataHub-style metadata entities and immutable aspects."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import ORMExecuteState, Session

from aqp.metadata.exceptions import ImmutableAspectError
from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base, _uuid

logger = logging.getLogger(__name__)


class MetadataEntity(Base, ProjectScopedMixin):
    """One canonical metadata entity identified by URN."""

    __tablename__ = "metadata_entities"

    urn = Column(String(280), primary_key=True)
    entity_type = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EntityAspect(Base, ProjectScopedMixin):
    """Immutable, versioned aspect payload for a metadata entity."""

    __tablename__ = "entity_aspects"

    id = Column(String(36), primary_key=True, default=_uuid)
    urn = Column(
        String(280),
        ForeignKey("metadata_entities.urn", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    aspect_name = Column(String(80), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    payload = Column(JSON, nullable=False)
    payload_hash = Column(String(64), nullable=False, index=True)
    system_metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_by = Column(String(120), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "urn",
            "aspect_name",
            "version",
            name="uq_entity_aspects_urn_name_version",
        ),
        UniqueConstraint(
            "urn",
            "aspect_name",
            "payload_hash",
            name="uq_entity_aspects_urn_name_hash",
        ),
    )


def _block_aspect_update(_mapper: Any, _connection: Any, target: EntityAspect) -> None:
    raise ImmutableAspectError(
        aspect_id=str(target.id),
        urn=str(target.urn),
        aspect_name=str(target.aspect_name),
    )


def _block_bulk_aspect_update(execute_state: ORMExecuteState) -> None:
    """Guard against ORM bulk UPDATE calls that bypass mapper hooks."""
    if not execute_state.is_update:
        return
    table = getattr(execute_state.statement, "table", None)
    if table is None or getattr(table, "name", None) != EntityAspect.__tablename__:
        return
    raise ImmutableAspectError(
        aspect_id="<bulk-update>",
        urn="<bulk-update>",
        aspect_name="<bulk-update>",
    )


event.listen(EntityAspect, "before_update", _block_aspect_update)
event.listen(Session, "do_orm_execute", _block_bulk_aspect_update)


__all__ = ["MetadataEntity", "EntityAspect"]

