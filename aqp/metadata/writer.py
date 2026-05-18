"""Helpers for writing immutable metadata aspects."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aqp.metadata.urn import parse_urn
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity

logger = logging.getLogger(__name__)


class AspectWriterControl:
    """Thread-local controls for aspect write side effects."""

    _suppression_depth = threading.local()

    @classmethod
    @contextmanager
    def suppress(cls) -> Iterator[None]:
        local = cls._suppression_depth
        depth = int(getattr(local, "value", 0))
        local.value = depth + 1
        try:
            yield
        finally:
            local.value = max(depth, 0)


def _canonicalize_payload(payload_model: BaseModel) -> tuple[dict[str, Any], str]:
    payload_dict = payload_model.model_dump(mode="json", by_alias=True)
    canonical = json.dumps(
        payload_dict,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload_dict, payload_hash


def write_aspect(
    session: Session,
    urn: str,
    aspect_name: str,
    payload_model: BaseModel,
    *,
    created_by: str | None = None,
    system_metadata: dict[str, Any] | None = None,
) -> EntityAspect:
    """Insert an immutable aspect version if payload changed.

    The helper is idempotent on ``(urn, aspect_name, payload_hash)`` and
    never mutates an existing row. The caller owns transaction boundaries.
    """
    parsed = parse_urn(urn)
    aspect_name_clean = str(aspect_name or "").strip()
    if not aspect_name_clean:
        raise ValueError("aspect_name cannot be empty")

    payload, payload_hash = _canonicalize_payload(payload_model)
    metadata_row = session.get(MetadataEntity, urn)
    if metadata_row is None:
        metadata_row = MetadataEntity(
            urn=urn,
            entity_type=parsed.entity_type,
        )
        session.add(metadata_row)
        session.flush()

    existing = (
        session.execute(
            select(EntityAspect)
            .where(
                EntityAspect.urn == urn,
                EntityAspect.aspect_name == aspect_name_clean,
                EntityAspect.payload_hash == payload_hash,
            )
            .order_by(EntityAspect.version.desc())
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing

    current_version = (
        session.execute(
            select(func.max(EntityAspect.version)).where(
                EntityAspect.urn == urn,
                EntityAspect.aspect_name == aspect_name_clean,
            )
        )
        .scalar_one_or_none()
        or 0
    )
    next_version = int(current_version) + 1
    row = EntityAspect(
        urn=urn,
        aspect_name=aspect_name_clean,
        version=next_version,
        payload=payload,
        payload_hash=payload_hash,
        system_metadata=dict(system_metadata or {}),
        created_by=created_by,
    )
    session.add(row)
    session.flush()
    return row


__all__ = ["AspectWriterControl", "write_aspect"]

