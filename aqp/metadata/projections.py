"""Legacy-table projections for canonical metadata aspects."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from aqp.metadata.urn import parse_urn
from aqp.metadata.writer import AspectWriterControl
from aqp.persistence.models import DatasetCatalog
from aqp.persistence.models_aspects import EntityAspect
from aqp.persistence.models_entity_registry import EntityRow

logger = logging.getLogger(__name__)

_CAPTURE_KEY = "_aqp_aspect_projection_capture"
_LISTENER_TARGET_IDS: set[int] = set()


def _normalise_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _provider_from_identifier(iceberg_identifier: str) -> str:
    namespace, _, _table = iceberg_identifier.rpartition(".")
    if not namespace:
        return "aqp"
    head = namespace.split(".", 1)[0]
    if head.startswith("aqp_"):
        return head[4:] or "aqp"
    return head or "aqp"


def _dataset_name_from_identifier(iceberg_identifier: str) -> str:
    _namespace, _sep, table_name = iceberg_identifier.rpartition(".")
    return table_name or iceberg_identifier


def _fill_if_null(obj: Any, field: str, value: Any) -> None:
    if value is None:
        return
    if getattr(obj, field) is None:
        setattr(obj, field, value)


def _table_exists(session: Session, table_name: str) -> bool:
    cache = session.info.setdefault("_aqp_aspect_projection_table_cache", {})
    if table_name in cache:
        return bool(cache[table_name])
    try:
        exists = bool(inspect(session.connection()).has_table(table_name))
    except Exception:
        exists = False
    cache[table_name] = exists
    return exists


def _ensure_dataset_catalog(
    session: Session,
    *,
    iceberg_identifier: str,
    seed_payload: dict[str, Any] | None = None,
) -> DatasetCatalog:
    row = (
        session.execute(
            select(DatasetCatalog).where(
                DatasetCatalog.iceberg_identifier == iceberg_identifier
            )
        )
        .scalars()
        .first()
    )
    payload = dict(seed_payload or {})
    if row is None:
        row = DatasetCatalog(
            iceberg_identifier=iceberg_identifier,
            name=_normalise_text(payload.get("name"))
            or _dataset_name_from_identifier(iceberg_identifier),
            provider=_normalise_text(payload.get("provider"))
            or _provider_from_identifier(iceberg_identifier),
            domain=_normalise_text(payload.get("domain")) or "market.bars",
            frequency=_normalise_text(payload.get("frequency")),
            storage_uri=_normalise_text(payload.get("storage_uri")),
            description=_normalise_text(payload.get("description")),
            medallion_layer=_normalise_text(payload.get("medallion_layer")),
            schema_json=dict(payload.get("schema_json") or {}),
            tags=list(payload.get("tags") or []),
            meta=dict(payload.get("meta") or {}),
        )
        session.add(row)
        return row

    _fill_if_null(row, "name", _normalise_text(payload.get("name")))
    _fill_if_null(row, "provider", _normalise_text(payload.get("provider")))
    _fill_if_null(row, "domain", _normalise_text(payload.get("domain")))
    _fill_if_null(row, "frequency", _normalise_text(payload.get("frequency")))
    _fill_if_null(row, "storage_uri", _normalise_text(payload.get("storage_uri")))
    _fill_if_null(row, "description", _normalise_text(payload.get("description")))
    _fill_if_null(
        row,
        "medallion_layer",
        _normalise_text(payload.get("medallion_layer")),
    )
    _fill_if_null(row, "schema_json", payload.get("schema_json"))
    _fill_if_null(row, "tags", payload.get("tags"))
    _fill_if_null(row, "meta", payload.get("meta"))
    _fill_if_null(row, "iceberg_identifier", iceberg_identifier)
    if hasattr(row, "updated_at"):
        row.updated_at = datetime.utcnow()
    return row


def _project_dataset_properties(session: Session, aspect: EntityAspect) -> None:
    if not _table_exists(session, DatasetCatalog.__tablename__):
        return
    parsed = parse_urn(aspect.urn)
    payload = dict(aspect.payload or {})
    _ensure_dataset_catalog(
        session,
        iceberg_identifier=parsed.id,
        seed_payload=payload,
    )


def _project_business_metadata(session: Session, aspect: EntityAspect) -> None:
    if not _table_exists(session, DatasetCatalog.__tablename__):
        return
    parsed = parse_urn(aspect.urn)
    row = _ensure_dataset_catalog(session, iceberg_identifier=parsed.id)
    row.business_metadata = dict(aspect.payload or {})
    if hasattr(row, "updated_at"):
        row.updated_at = datetime.utcnow()


def _project_data_contract(session: Session, aspect: EntityAspect) -> None:
    if not _table_exists(session, DatasetCatalog.__tablename__):
        return
    parsed = parse_urn(aspect.urn)
    row = _ensure_dataset_catalog(session, iceberg_identifier=parsed.id)
    row.data_contract_json = dict(aspect.payload or {})
    if hasattr(row, "updated_at"):
        row.updated_at = datetime.utcnow()


def _project_entity_properties(session: Session, aspect: EntityAspect) -> None:
    if not _table_exists(session, EntityRow.__tablename__):
        return
    parsed = parse_urn(aspect.urn)
    payload = dict(aspect.payload or {})
    entity_id = parsed.id
    row = session.get(EntityRow, entity_id)
    if row is None:
        row = EntityRow(
            id=entity_id,
            kind=_normalise_text(payload.get("kind")) or parsed.entity_type,
            canonical_name=_normalise_text(payload.get("canonical_name"))
            or _normalise_text(payload.get("name"))
            or entity_id,
            short_name=_normalise_text(payload.get("short_name")),
            primary_identifier=_normalise_text(payload.get("primary_identifier")),
            primary_identifier_scheme=_normalise_text(
                payload.get("primary_identifier_scheme")
            ),
            description=_normalise_text(payload.get("description")),
            attributes=dict(payload.get("attributes") or {}),
            tags=list(payload.get("tags") or []),
            source_dataset=_normalise_text(payload.get("source_dataset")),
            source_extractor=_normalise_text(payload.get("source_extractor")),
            is_canonical=bool(payload.get("is_canonical", True)),
        )
        confidence = payload.get("confidence")
        if confidence is not None:
            try:
                row.confidence = float(confidence)
            except (TypeError, ValueError):
                pass
        session.add(row)
        return

    if payload.get("kind") is not None:
        row.kind = _normalise_text(payload.get("kind")) or row.kind
    if payload.get("canonical_name") is not None:
        row.canonical_name = _normalise_text(payload.get("canonical_name")) or row.canonical_name
    if payload.get("short_name") is not None:
        row.short_name = _normalise_text(payload.get("short_name"))
    if payload.get("primary_identifier") is not None:
        row.primary_identifier = _normalise_text(payload.get("primary_identifier"))
    if payload.get("primary_identifier_scheme") is not None:
        row.primary_identifier_scheme = _normalise_text(
            payload.get("primary_identifier_scheme")
        )
    if payload.get("description") is not None:
        row.description = _normalise_text(payload.get("description"))
    if payload.get("attributes") is not None:
        row.attributes = dict(payload.get("attributes") or {})
    if payload.get("tags") is not None:
        row.tags = list(payload.get("tags") or [])
    if payload.get("source_dataset") is not None:
        row.source_dataset = _normalise_text(payload.get("source_dataset"))
    if payload.get("source_extractor") is not None:
        row.source_extractor = _normalise_text(payload.get("source_extractor"))
    if payload.get("is_canonical") is not None:
        row.is_canonical = bool(payload.get("is_canonical"))
    if payload.get("confidence") is not None:
        try:
            row.confidence = float(payload.get("confidence"))
        except (TypeError, ValueError):
            pass
    row.updated_at = datetime.utcnow()


def _project_lineage_edge(_session: Session, _aspect: EntityAspect) -> None:
    # Intentionally no-op: data_lineage_events remains the legacy projection.
    return


def _capture_new_aspects(session: Session, _flush_context: Any, _instances: Any) -> None:
    if getattr(AspectWriterControl._suppression_depth, "value", 0) > 0:
        session.info.pop(_CAPTURE_KEY, None)
        return
    captured = [row for row in session.new if isinstance(row, EntityAspect)]
    if captured:
        session.info[_CAPTURE_KEY] = captured


def _project_new_aspects(session: Session, _flush_context: Any) -> None:
    if getattr(AspectWriterControl._suppression_depth, "value", 0) > 0:
        session.info.pop(_CAPTURE_KEY, None)
        return
    captured = session.info.pop(_CAPTURE_KEY, None)
    if not captured:
        return

    for row in captured:
        try:
            if row.aspect_name == "datasetProperties":
                _project_dataset_properties(session, row)
            elif row.aspect_name == "businessMetadata":
                _project_business_metadata(session, row)
            elif row.aspect_name == "dataContract":
                _project_data_contract(session, row)
            elif row.aspect_name == "entityProperties":
                _project_entity_properties(session, row)
            elif row.aspect_name == "lineageEdge":
                _project_lineage_edge(session, row)
        except Exception:
            logger.debug(
                "Aspect projection failed for urn=%s aspect=%s",
                row.urn,
                row.aspect_name,
                exc_info=True,
            )


def _resolve_event_target(_session_factory: Any) -> type[Session]:
    # Register against the SQLAlchemy Session base class so the listeners
    # apply to every sessionmaker without forcing eager engine creation.
    return Session


def register_projection_listeners(session_factory: Any) -> None:
    """Register projection listeners on a Session or sessionmaker target."""
    target = _resolve_event_target(session_factory)
    target_id = id(target)
    if target_id in _LISTENER_TARGET_IDS:
        return
    event.listen(target, "before_flush", _capture_new_aspects)
    event.listen(target, "after_flush_postexec", _project_new_aspects)
    _LISTENER_TARGET_IDS.add(target_id)


from aqp.persistence.db import SessionLocal  # noqa: E402

register_projection_listeners(SessionLocal)


__all__ = ["register_projection_listeners"]

