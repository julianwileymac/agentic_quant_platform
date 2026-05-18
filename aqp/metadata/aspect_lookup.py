"""Read helpers that resolve aspects from entity_aspects by URN."""
from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from aqp.metadata import parse_urn
from aqp.metadata.openmetadata import MlModel, Pipeline
from aqp.persistence.db import get_session
from aqp.persistence.models_aspects import EntityAspect


def _fetch_aspect_payload(
    session: Session,
    *,
    urn: str,
    aspect_name: str,
    version: int | None,
) -> dict[str, Any] | None:
    """Return one aspect payload row for a URN/aspect pair."""
    stmt = select(EntityAspect.payload).where(
        EntityAspect.urn == urn,
        EntityAspect.aspect_name == aspect_name,
    )
    if version is None:
        stmt = stmt.order_by(desc(EntityAspect.version)).limit(1)
    else:
        stmt = stmt.where(EntityAspect.version == int(version)).limit(1)
    payload = session.execute(stmt).scalar_one_or_none()
    return payload if isinstance(payload, dict) else None


def load_aspect(
    urn: str,
    aspect_name: str,
    *,
    version: int | None = None,
    session: Session | None = None,
) -> dict[str, Any] | None:
    """Load a named aspect payload by URN.

    When ``version`` is omitted, returns the latest immutable aspect version.
    """
    parse_urn(urn)
    if session is not None:
        return _fetch_aspect_payload(
            session,
            urn=urn,
            aspect_name=aspect_name,
            version=version,
        )
    with get_session() as owned_session:
        return _fetch_aspect_payload(
            owned_session,
            urn=urn,
            aspect_name=aspect_name,
            version=version,
        )


def load_ml_model(urn: str, *, version: int | None = None) -> MlModel | None:
    """Load and validate the ``mlModelMetadata`` aspect for ``urn``."""
    payload = load_aspect(urn, "mlModelMetadata", version=version)
    if payload is None:
        return None
    return MlModel.model_validate(payload)


def load_pipeline(urn: str, *, version: int | None = None) -> Pipeline | None:
    """Load and validate the ``pipelineMetadata`` aspect for ``urn``."""
    payload = load_aspect(urn, "pipelineMetadata", version=version)
    if payload is None:
        return None
    return Pipeline.model_validate(payload)


__all__ = ["load_aspect", "load_ml_model", "load_pipeline"]
