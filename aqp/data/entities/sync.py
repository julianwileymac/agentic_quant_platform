"""Entity graph synchronization helpers for instruments and dataset coverage."""
from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import select

from aqp.config import settings
from aqp.data.entities import registry as entity_registry
from aqp.persistence.models import DatasetCatalog, DatasetVersion, Instrument

logger = logging.getLogger(__name__)

_ACTIVE_CACHE: tuple[float, list[dict[str, Any]]] | None = None


def _instrument_payload(row: Instrument) -> dict[str, Any]:
    return {
        "id": row.id,
        "vt_symbol": row.vt_symbol,
        "ticker": row.ticker,
        "exchange": row.exchange,
        "asset_class": row.asset_class,
        "security_type": row.security_type,
        "issuer_id": row.issuer_id,
        "identifiers": dict(row.identifiers or {}),
        "sector": row.sector,
        "industry": row.industry,
        "region": row.region,
        "currency": row.currency,
        "is_active": bool(row.is_active),
        "tags": list(row.tags or []),
        "meta": dict(row.meta or {}),
        "updated_at": row.updated_at,
    }


def active_instruments(*, session: Any, limit: int = 5000, refresh: bool = False) -> list[dict[str, Any]]:
    """Return cached active instrument payloads from the security master."""
    global _ACTIVE_CACHE
    ttl = max(1, int(settings.active_instrument_cache_ttl_seconds or 300))
    now = time.monotonic()
    if not refresh and _ACTIVE_CACHE and now - _ACTIVE_CACHE[0] < ttl:
        return list(_ACTIVE_CACHE[1])
    rows = (
        session.execute(
            select(Instrument)
            .where(Instrument.is_active.is_(True))
            .order_by(Instrument.ticker.asc())
            .limit(max(1, int(limit)))
        )
        .scalars()
        .all()
    )
    payloads = [_instrument_payload(row) for row in rows]
    _ACTIVE_CACHE = (now, payloads)
    return list(payloads)


def clear_active_instrument_cache() -> None:
    global _ACTIVE_CACHE
    _ACTIVE_CACHE = None


def upsert_instrument_entity(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Upsert one instrument as a canonical ``security`` entity."""
    vt_symbol = str(payload.get("vt_symbol") or "").strip()
    if not vt_symbol:
        return None
    entity = entity_registry.upsert_entity(
        kind="security",
        canonical_name=str(payload.get("ticker") or vt_symbol),
        short_name=str(payload.get("ticker") or vt_symbol),
        primary_identifier=vt_symbol,
        primary_identifier_scheme="vt_symbol",
        instrument_id=str(payload.get("id") or "") or None,
        issuer_id=str(payload.get("issuer_id") or "") or None,
        attributes={
            "vt_symbol": vt_symbol,
            "ticker": payload.get("ticker"),
            "exchange": payload.get("exchange"),
            "asset_class": payload.get("asset_class"),
            "security_type": payload.get("security_type"),
            "sector": payload.get("sector"),
            "industry": payload.get("industry"),
            "region": payload.get("region"),
            "currency": payload.get("currency"),
            "is_active": payload.get("is_active"),
            **dict(payload.get("meta") or {}),
        },
        tags=sorted({"instrument", "security", *(payload.get("tags") or [])}),
        source_dataset="instrument_master",
        source_extractor="aqp.instrument_cache",
    )
    if not entity:
        return None
    entity_id = str(entity["id"])
    entity_registry.link_entity_identifier(
        entity_id=entity_id,
        scheme="vt_symbol",
        value=vt_symbol,
        source="instrument_master",
        confidence=1.0,
    )
    ticker = str(payload.get("ticker") or "").strip()
    if ticker:
        entity_registry.link_entity_identifier(
            entity_id=entity_id,
            scheme="ticker",
            value=ticker,
            source="instrument_master",
            confidence=0.95,
        )
    for scheme, value in dict(payload.get("identifiers") or {}).items():
        if value:
            entity_registry.link_entity_identifier(
                entity_id=entity_id,
                scheme=str(scheme),
                value=str(value),
                source="instrument_master",
            )
    return entity


def sync_active_instruments_to_graph(*, session: Any, limit: int = 5000) -> dict[str, Any]:
    """Seed the configured graph store from active instruments."""
    payloads = active_instruments(session=session, limit=limit, refresh=True)
    upserted = 0
    for payload in payloads:
        if upsert_instrument_entity(payload):
            upserted += 1
    return {"seen": len(payloads), "upserted": upserted}


def sync_dataset_version_entities(
    *,
    session: Any,
    catalog: DatasetCatalog,
    version: DatasetVersion,
    vt_symbols: Iterable[str],
    coverage_start: datetime | None = None,
    coverage_end: datetime | None = None,
) -> dict[str, Any]:
    """Link a dataset version to the instrument entities it describes."""
    symbols = sorted({str(v).strip() for v in vt_symbols if str(v).strip()})
    if not settings.entity_graph_sync_enabled or not symbols:
        return {"linked": 0, "symbols": len(symbols)}
    rows = (
        session.execute(select(Instrument).where(Instrument.vt_symbol.in_(symbols)))
        .scalars()
        .all()
    )
    linked = 0
    for instrument in rows:
        entity = upsert_instrument_entity(_instrument_payload(instrument))
        if not entity:
            continue
        entity_registry.attach_entity_to_dataset(
            entity_id=str(entity["id"]),
            dataset_catalog_id=catalog.id,
            dataset_version_id=version.id,
            iceberg_identifier=catalog.iceberg_identifier,
            row_count=version.row_count,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            role="describes",
            meta={
                "provider": catalog.provider,
                "domain": catalog.domain,
                "dataset_name": catalog.name,
                "vt_symbol": instrument.vt_symbol,
            },
        )
        linked += 1
    return {"linked": linked, "symbols": len(symbols)}


__all__ = [
    "active_instruments",
    "clear_active_instrument_cache",
    "sync_active_instruments_to_graph",
    "sync_dataset_version_entities",
    "upsert_instrument_entity",
]
