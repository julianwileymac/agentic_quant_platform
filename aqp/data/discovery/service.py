"""Unified discovery service.

Merges four sources into a single :class:`DiscoveryEntry` stream so
the frontend browser can show ingested, pending, orphan, and
external-only entries side-by-side. Reads are tolerant of every
source being unavailable individually so a fresh cluster boot still
produces a usable browser.

CRUD on uningested entries goes through ``DatasetCatalog`` rows with
``is_ingested=False``, ``dataset_kind="external"``, and the
descriptor stuffed into ``external_spec_json``. This keeps a single
ORM table as source of truth while satisfying the "external sources
are first-class catalog citizens" requirement.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError

from aqp.data.discovery.types import (
    CreateExternalEntryRequest,
    DiscoveryEntry,
    DiscoveryLifecycleState,
    DiscoveryPage,
    UpdateEntryRequest,
)
from aqp.persistence.db import get_session
from aqp.persistence.models import DatasetCatalog

logger = logging.getLogger(__name__)


class DiscoveryService:
    """Collate ingested + pending + orphan + external-only entries."""

    def list(
        self,
        *,
        lifecycle: DiscoveryLifecycleState | None = None,
        provider: str | None = None,
        kind: str | None = None,
        search: str | None = None,
        limit: int = 100,
        cursor: int = 0,
    ) -> DiscoveryPage:
        entries: list[DiscoveryEntry] = []
        seen: set[tuple[str, str]] = set()
        try:
            with get_session() as session:
                for entry in self._dataset_catalog_entries(session):
                    seen.add(_dedupe_key(entry))
                    entries.append(entry)
                for entry in self._source_library_entries(session, seen=seen):
                    seen.add(_dedupe_key(entry))
                    entries.append(entry)
                for entry in self._airbyte_connection_entries(session, seen=seen):
                    seen.add(_dedupe_key(entry))
                    entries.append(entry)
        except Exception as exc:  # noqa: BLE001
            logger.info("discovery: postgres unreachable (%s)", exc)
        for entry in self._iceberg_orphans(seen):
            seen.add(_dedupe_key(entry))
            entries.append(entry)
        # Now apply filters.
        filtered = list(self._apply_filters(entries, lifecycle, provider, kind, search))
        filtered.sort(key=lambda e: (e.lifecycle_state, e.name.lower()))
        total = len(filtered)
        page = filtered[max(0, int(cursor)) : max(0, int(cursor)) + max(1, int(limit))]
        next_cursor: int | None = None
        consumed = max(0, int(cursor)) + len(page)
        if consumed < total and len(page) >= int(limit):
            next_cursor = consumed
        by_state: dict[str, int] = {}
        for entry in entries:
            by_state[entry.lifecycle_state] = by_state.get(entry.lifecycle_state, 0) + 1
        return DiscoveryPage(items=page, total=total, next_cursor=next_cursor, by_lifecycle=by_state)

    def get(self, entry_id: str) -> DiscoveryEntry | None:
        page = self.list(limit=10_000)
        for entry in page.items:
            if entry.id == entry_id:
                return entry
        return None

    # -------------------------------------------------- mutations
    def create_external(
        self,
        payload: CreateExternalEntryRequest,
        *,
        owner_user_id: str | None = None,
        workspace_id: str | None = None,
        project_id: str | None = None,
    ) -> DiscoveryEntry:
        external_spec = {
            "source_uri": payload.source_uri,
            "docs_url": payload.docs_url,
            "intent_kind": payload.suggested_kind or "external",
            "suggested_connector": payload.suggested_connector,
        }
        with get_session() as session:
            row = DatasetCatalog(
                name=payload.name.strip(),
                provider=(payload.provider or "self_service").strip(),
                domain=(payload.domain or "user.dataset").strip(),
                description=payload.description,
                tags=list(payload.tags or []),
                load_mode="discovered",
                source_uri=payload.source_uri,
                business_metadata=dict(payload.business_metadata or {}),
                data_contract_json=dict(payload.data_contract or {}),
                dataset_kind=str(payload.suggested_kind or "external"),
                is_ingested=False,
                external_spec_json=external_spec,
                updated_at=datetime.utcnow(),
            )
            if owner_user_id:
                row.owner_user_id = owner_user_id
            if workspace_id:
                row.workspace_id = workspace_id
            if project_id:
                row.project_id = project_id
            session.add(row)
            session.commit()
            session.refresh(row)
            entry = self._row_to_entry(row)
        try:
            from aqp.cache import cache_write_through

            cache_write_through("datasets", _entry_cache_payload(entry))
        except Exception:  # noqa: BLE001
            pass
        try:
            from aqp.data.catalog.lineage import LineageEvent, LineageWriter

            LineageWriter().record(
                LineageEvent(
                    transform_kind="discovery.created",
                    target_table_id=entry.id,
                    summary=f"discovery entry created: {entry.name}",
                    actor=owner_user_id,
                    actor_kind="user" if owner_user_id else "system",
                    workspace_id=workspace_id,
                    project_id=project_id,
                    owner_user_id=owner_user_id,
                    details={"name": entry.name, "provider": entry.provider},
                )
            )
        except Exception:  # noqa: BLE001
            logger.debug("discovery.created lineage emit skipped", exc_info=True)
        return entry

    def patch(self, entry_id: str, payload: UpdateEntryRequest) -> DiscoveryEntry | None:
        with get_session() as session:
            row = session.execute(
                select(DatasetCatalog).where(DatasetCatalog.id == entry_id).limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None
            changed = False
            if payload.description is not None:
                row.description = payload.description
                changed = True
            if payload.tags is not None:
                row.tags = list(payload.tags or [])
                changed = True
            if payload.business_metadata is not None:
                row.business_metadata = dict(payload.business_metadata or {})
                changed = True
            if payload.data_contract is not None:
                row.data_contract_json = dict(payload.data_contract or {})
                changed = True
            external_spec = dict(row.external_spec_json or {})
            external_changed = False
            if payload.source_uri is not None:
                external_spec["source_uri"] = payload.source_uri
                row.source_uri = payload.source_uri
                external_changed = True
            if payload.docs_url is not None:
                external_spec["docs_url"] = payload.docs_url
                external_changed = True
            if payload.suggested_connector is not None:
                external_spec["suggested_connector"] = payload.suggested_connector
                external_changed = True
            if payload.suggested_kind is not None:
                external_spec["intent_kind"] = payload.suggested_kind
                row.dataset_kind = payload.suggested_kind
                external_changed = True
            if external_changed:
                row.external_spec_json = external_spec
                changed = True
            if changed:
                row.updated_at = datetime.utcnow()
                session.add(row)
                session.commit()
                session.refresh(row)
            entry = self._row_to_entry(row)
        try:
            from aqp.cache import cache_write_through

            cache_write_through("datasets", _entry_cache_payload(entry))
        except Exception:  # noqa: BLE001
            pass
        return entry

    def delete(self, entry_id: str) -> bool:
        """Delete an external (uningested) entry. Refuses ingested rows."""
        with get_session() as session:
            row = session.execute(
                select(DatasetCatalog).where(DatasetCatalog.id == entry_id).limit(1)
            ).scalar_one_or_none()
            if row is None:
                return False
            if bool(getattr(row, "is_ingested", False)):
                raise PermissionError(
                    "ingested datasets cannot be deleted via the discovery surface"
                )
            session.delete(row)
            session.commit()
        try:
            from aqp.cache import cache_invalidate

            cache_invalidate("datasets", entry_id, name=row.name if row else None)
        except Exception:  # noqa: BLE001
            pass
        return True

    def promote(
        self,
        entry_id: str,
        *,
        target_kind: str = "airbyte_builder",
        notes: str | None = None,
        actor: str | None = None,
        workspace_id: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Emit a lineage event + return a deep-link the frontend follows."""
        entry = self.get(entry_id)
        if entry is None:
            raise LookupError(f"discovery entry {entry_id!r} not found")
        builder_state = {
            "name": entry.name,
            "provider": entry.provider,
            "domain": entry.domain,
            "description": entry.description,
            "source_uri": entry.source_uri,
            "docs_url": entry.docs_url,
            "suggested_connector": entry.suggested_connector,
            "suggested_kind": entry.suggested_kind,
            "tags": list(entry.tags or []),
            "business_metadata": dict(entry.business_metadata or {}),
            "external_spec": dict(entry.external_spec or {}),
        }
        if target_kind == "fetcher_stub":
            redirect_url = (
                "/airbyte/builder?"
                + urlencode(
                    {"from": "discovery", "entry_id": entry_id, "mode": "fetcher_stub"}
                )
            )
        else:
            redirect_url = (
                "/airbyte/builder?"
                + urlencode({"from": "discovery", "entry_id": entry_id})
            )
        try:
            from aqp.data.catalog.lineage import LineageEvent, LineageWriter

            LineageWriter().record(
                LineageEvent(
                    transform_kind="discovery.promoted",
                    target_table_id=entry_id,
                    summary=f"promoted to {target_kind}: {entry.name}",
                    actor=actor,
                    actor_kind="user" if actor else "system",
                    workspace_id=workspace_id,
                    project_id=project_id,
                    details={
                        "target_kind": target_kind,
                        "notes": notes,
                        "redirect_url": redirect_url,
                    },
                )
            )
        except Exception:  # noqa: BLE001
            logger.debug("discovery.promoted lineage emit skipped", exc_info=True)
        return {
            "entry_id": entry_id,
            "target_kind": target_kind,
            "redirect_url": redirect_url,
            "builder_state": builder_state,
        }

    # -------------------------------------------------- collators
    def _dataset_catalog_entries(self, session: Any) -> Iterable[DiscoveryEntry]:
        try:
            rows = session.execute(
                select(DatasetCatalog).order_by(desc(DatasetCatalog.updated_at)).limit(2000)
            ).scalars().all()
        except SQLAlchemyError as exc:
            logger.info("discovery: DatasetCatalog read skipped: %s", exc)
            return []
        return [self._row_to_entry(row) for row in rows]

    def _source_library_entries(
        self,
        session: Any,
        *,
        seen: set[tuple[str, str]],
    ) -> Iterable[DiscoveryEntry]:
        try:
            from aqp.persistence.models_data_control import SourceLibraryEntry
        except Exception:  # noqa: BLE001
            return []
        try:
            rows = session.execute(
                select(SourceLibraryEntry).limit(1000)
            ).scalars().all()
        except SQLAlchemyError as exc:
            logger.info("discovery: SourceLibraryEntry read skipped: %s", exc)
            return []
        out: list[DiscoveryEntry] = []
        for row in rows:
            key = (str(row.source_name or "").lower(), str(row.display_name or "").lower())
            if key in seen:
                continue
            entry = DiscoveryEntry(
                id=f"library:{row.id}",
                name=str(row.display_name or row.source_name or row.id),
                provider=str(row.source_name or "external"),
                lifecycle_state="external_only",
                dataset_kind="external",
                is_ingested=False,
                docs_url=row.docs_url,
                source_uri=row.import_uri or row.reference_path,
                tags=list(row.tags or []),
                external_spec={
                    "source_library_id": row.id,
                    "import_uri": row.import_uri,
                    "reference_path": row.reference_path,
                    "default_node": row.default_node,
                    "metadata": dict(row.metadata_json or {}),
                    "pipeline_hints": dict(row.pipeline_hints or {}),
                    "intent_kind": "external",
                },
                suggested_connector=row.default_node,
                suggested_kind="external",
                updated_at=row.updated_at,
            )
            out.append(entry)
            seen.add(key)
        return out

    def _airbyte_connection_entries(
        self,
        session: Any,
        *,
        seen: set[tuple[str, str]],
    ) -> Iterable[DiscoveryEntry]:
        try:
            from aqp.persistence.models_airbyte import AirbyteConnectionRow
        except Exception:  # noqa: BLE001
            return []
        try:
            rows = session.execute(
                select(AirbyteConnectionRow).limit(500)
            ).scalars().all()
        except SQLAlchemyError as exc:
            logger.info("discovery: AirbyteConnectionRow read skipped: %s", exc)
            return []
        out: list[DiscoveryEntry] = []
        for row in rows:
            key = ("airbyte", str(row.name or row.id).lower())
            if key in seen:
                continue
            lifecycle: DiscoveryLifecycleState = (
                "ingested" if row.last_sync_status == "succeeded" else "pending"
            )
            entry = DiscoveryEntry(
                id=f"airbyte:{row.id}",
                name=str(row.name or row.id),
                provider="airbyte",
                lifecycle_state=lifecycle,
                dataset_kind="external",
                is_ingested=lifecycle == "ingested",
                namespace=str(row.namespace or ""),
                docs_url=None,
                source_uri=str(row.airbyte_connection_id or ""),
                external_spec={
                    "airbyte_row_id": row.id,
                    "source_connector_id": row.source_connector_id,
                    "destination_connector_id": row.destination_connector_id,
                    "intent_kind": "airbyte",
                },
                suggested_connector=str(row.source_connector_id or ""),
                suggested_kind="airbyte",
                airbyte_connection_id=row.airbyte_connection_id,
                updated_at=getattr(row, "updated_at", None) or getattr(row, "created_at", None),
            )
            out.append(entry)
            seen.add(key)
        return out

    def _iceberg_orphans(self, seen: set[tuple[str, str]]) -> Iterable[DiscoveryEntry]:
        try:
            from aqp.data import iceberg_catalog

            tables = iceberg_catalog.list_tables() or []
        except Exception:  # noqa: BLE001
            return []
        out: list[DiscoveryEntry] = []
        for identifier in tables:
            ns, _, name = identifier.partition(".")
            if not name:
                continue
            key = (str(ns).lower(), str(name).lower())
            if key in seen:
                continue
            entry = DiscoveryEntry(
                id=f"orphan:{identifier}",
                name=str(name),
                provider="iceberg",
                lifecycle_state="orphan",
                dataset_kind="iceberg",
                is_ingested=True,
                iceberg_identifier=identifier,
                namespace=ns,
                medallion_layer=_layer_for_namespace(ns),
                tags=[],
                external_spec={"intent_kind": "iceberg-orphan"},
                suggested_kind="iceberg",
            )
            out.append(entry)
            seen.add(key)
        return out

    # -------------------------------------------------- helpers
    def _row_to_entry(self, row: DatasetCatalog) -> DiscoveryEntry:
        external_spec = dict(getattr(row, "external_spec_json", None) or {})
        effective_description = str(getattr(row, "description", "") or "").strip()
        if not effective_description:
            llm_annotations = getattr(row, "llm_annotations", None)
            if isinstance(llm_annotations, dict):
                effective_description = str(
                    llm_annotations.get("description") or ""
                ).strip()
        is_ingested = bool(
            getattr(row, "is_ingested", None)
            if getattr(row, "is_ingested", None) is not None
            else bool(getattr(row, "iceberg_identifier", None))
        )
        if is_ingested:
            lifecycle: DiscoveryLifecycleState = "ingested"
        elif external_spec.get("intent_kind"):
            lifecycle = (
                "external_only"
                if external_spec.get("intent_kind") in {"external", "iceberg-orphan", "airbyte"}
                else "pending"
            )
        else:
            lifecycle = "pending"
        identifier = str(row.iceberg_identifier or "")
        ns = identifier.partition(".")[0] if identifier else None
        return DiscoveryEntry(
            id=str(row.id),
            name=str(row.name or row.id),
            provider=str(row.provider or "self_service"),
            domain=str(row.domain) if getattr(row, "domain", None) else None,
            lifecycle_state=lifecycle,
            dataset_kind=str(getattr(row, "dataset_kind", None) or "")
            or ("iceberg" if identifier else "external"),
            is_ingested=is_ingested,
            iceberg_identifier=identifier or None,
            namespace=ns or None,
            medallion_layer=getattr(row, "medallion_layer", None),
            description=effective_description or None,
            docs_url=external_spec.get("docs_url"),
            source_uri=row.source_uri or external_spec.get("source_uri"),
            tags=list(row.tags or []),
            spec_hash=getattr(row, "spec_hash", None),
            external_spec=external_spec,
            business_metadata=dict(getattr(row, "business_metadata", None) or {}),
            data_contract=dict(getattr(row, "data_contract_json", None) or {}),
            suggested_connector=external_spec.get("suggested_connector"),
            suggested_kind=external_spec.get("intent_kind") or getattr(row, "dataset_kind", None),
            updated_at=getattr(row, "updated_at", None),
        )

    def _apply_filters(
        self,
        entries: Iterable[DiscoveryEntry],
        lifecycle: DiscoveryLifecycleState | None,
        provider: str | None,
        kind: str | None,
        search: str | None,
    ) -> Iterable[DiscoveryEntry]:
        needle = (search or "").strip().lower()
        for entry in entries:
            if lifecycle and entry.lifecycle_state != lifecycle:
                continue
            if provider and (entry.provider or "").lower() != provider.lower():
                continue
            if kind and (entry.dataset_kind or "").lower() != kind.lower():
                continue
            if needle:
                hay = " ".join(
                    str(part)
                    for part in (entry.name, entry.provider, entry.description, entry.iceberg_identifier)
                    if part
                ).lower()
                if needle not in hay:
                    continue
            yield entry


def _dedupe_key(entry: DiscoveryEntry) -> tuple[str, str]:
    """Stable key so the four collators don't double-count the same entity."""
    return (str(entry.provider or "").lower(), str(entry.name or "").lower())


def _entry_cache_payload(entry: DiscoveryEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "name": entry.name,
        "provider": entry.provider,
        "domain": entry.domain or "",
        "iceberg_identifier": entry.iceberg_identifier or "",
        "medallion_layer": entry.medallion_layer or "",
        "dataset_kind": entry.dataset_kind or "",
        "is_ingested": "true" if entry.is_ingested else "false",
        "lifecycle_state": entry.lifecycle_state,
        "tags": list(entry.tags or []),
    }


_LAYER_PREFIX_TO_LAYER = {
    "aqp_bronze_": "bronze",
    "aqp_silver_": "silver",
    "aqp_gold_": "gold",
}


def _layer_for_namespace(namespace: str | None) -> str | None:
    if not namespace:
        return None
    for prefix, layer in _LAYER_PREFIX_TO_LAYER.items():
        if namespace.startswith(prefix):
            return layer
    return None


__all__ = ["DiscoveryService"]
