"""Background prefetcher that populates the metadata cache.

Runs on FastAPI startup (via :mod:`aqp.cache.lifespan`) and periodically
afterward (Celery beat). Each ``run_full`` walks Postgres + the dataset
kind registry and replaces the eight cache categories in lockstep.
Write-through hooks (:mod:`aqp.cache.invalidation`) keep the cache live
between runs.

The prefetcher must be **safe to run when Postgres is empty**:
fresh-cluster bootstrap calls it before any datasets exist, so missing
tables / zero rows are normal. It must also be **safe to run when
Redis is unreachable**: the in-memory fallback handles every verb.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from aqp.cache.client import MetadataCache, get_cache
from aqp.cache.keys import (
    CACHE_CATEGORIES,
    by_id_hash,
    by_name_hash,
    category_stamp,
    names_zset,
)
from aqp.config import settings

logger = logging.getLogger(__name__)


class MetadataPrefetcher:
    """Populate :class:`MetadataCache` from authoritative sources."""

    def __init__(self, cache: MetadataCache | None = None) -> None:
        self.cache = cache or get_cache()

    # ------------------------------------------------------------------ entry points
    def run_full(self, session: Session | None = None) -> dict[str, int]:
        """Refresh every category. Returns ``{category: row_count}``."""
        results: dict[str, int] = {category: 0 for category in CACHE_CATEGORIES}
        # The dataset-kind registry is a process-local list; refresh it
        # first so it's available even when Postgres is unreachable.
        results["dataset_kinds"] = self._populate_dataset_kinds()
        if session is not None:
            self._populate_with_session(results, session)
            return results
        # Open a session ourselves; postgres may be down on first boot.
        try:
            from aqp.persistence.db import get_session
        except Exception as exc:  # noqa: BLE001
            logger.info("metadata prefetch skipped: cannot import get_session (%s)", exc)
            return results
        try:
            with get_session() as opened:
                self._populate_with_session(results, opened)
        except Exception as exc:  # noqa: BLE001
            logger.info("metadata prefetch skipped: postgres unreachable (%s)", exc)
        return results

    def _populate_with_session(
        self, results: dict[str, int], session: Session
    ) -> None:
        results["datasets"] = self._populate_datasets(session)
        results["namespaces"] = self._populate_namespaces(session)
        results["sink_kinds"] = self._populate_sink_kinds(session)
        results["sink_names"] = self._populate_sink_names(session)
        results["airbyte_connectors"] = self._populate_airbyte_connectors(session)
        results["projects"] = self._populate_projects(session)
        results["credentials"] = self._populate_credentials(session)

    def _stamp(self, pipe: Any, category: str) -> None:
        """Record a cache freshness stamp for the category."""
        try:
            pipe.set(category_stamp(category), datetime.utcnow().isoformat())  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    def _set_master_ttl(self, pipe: Any, key: str) -> None:
        ttl = max(60, int(settings.cache_master_ttl_s))
        try:
            pipe.expire(key, ttl)
        except Exception:  # noqa: BLE001
            pass

    def _set_instance_ttl(self, pipe: Any, key: str) -> None:
        ttl = max(60, int(settings.cache_instance_ttl_s))
        try:
            pipe.expire(key, ttl)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ populators
    def _populate_dataset_kinds(self) -> int:
        """Read the in-process dataset kind registry."""
        try:
            from aqp.data.datasets.registry import iter_dataset_kinds
        except Exception:  # noqa: BLE001
            return 0
        names = list(iter_dataset_kinds())
        if not names:
            return 0
        zkey = names_zset("dataset_kinds")
        self.cache.delete(zkey)
        self.cache.zadd(zkey, {name: 0.0 for name in names})
        for name in names:
            id_key = by_id_hash("dataset_kinds", name)
            self.cache.hset(id_key, {"name": name, "kind": name})
            self.cache.expire(id_key, settings.cache_master_ttl_s)
        self.cache.expire(zkey, settings.cache_master_ttl_s)
        self.cache.set_string(category_stamp("dataset_kinds"), datetime.utcnow().isoformat())
        return len(names)

    def _populate_datasets(self, session: Session) -> int:
        try:
            from aqp.persistence.models import DatasetCatalog
        except Exception:  # noqa: BLE001
            return 0
        try:
            rows = session.execute(
                select(DatasetCatalog).order_by(DatasetCatalog.name)
            ).scalars().all()
        except SQLAlchemyError as exc:
            logger.info("metadata prefetch datasets skipped: %s", exc)
            return 0
        zkey = names_zset("datasets")
        self.cache.delete(zkey)
        mapping: dict[str, float] = {}
        for row in rows:
            identifier = str(getattr(row, "id", "") or "")
            if not identifier:
                continue
            name = str(getattr(row, "name", "") or "")
            if not name:
                continue
            mapping[name] = 0.0
            payload = _dataset_payload(row)
            id_key = by_id_hash("datasets", identifier)
            self.cache.hset(id_key, payload)
            self.cache.expire(id_key, settings.cache_instance_ttl_s)
            name_key = by_name_hash("datasets", name)
            self.cache.hset(name_key, {"id": identifier})
            self.cache.expire(name_key, settings.cache_instance_ttl_s)
        if mapping:
            self.cache.zadd(zkey, mapping)
        self.cache.expire(zkey, settings.cache_instance_ttl_s)
        self.cache.set_string(category_stamp("datasets"), datetime.utcnow().isoformat())
        return len(rows)

    def _populate_namespaces(self, session: Session) -> int:
        try:
            from aqp.persistence.models import DatasetCatalog
        except Exception:  # noqa: BLE001
            return 0
        zkey = names_zset("namespaces")
        try:
            rows = session.execute(
                select(DatasetCatalog.iceberg_identifier).where(
                    DatasetCatalog.iceberg_identifier.is_not(None)
                )
            ).all()
        except SQLAlchemyError:
            return 0
        namespaces: set[str] = set()
        for (identifier,) in rows:
            if not identifier:
                continue
            namespace = str(identifier).split(".", 1)[0]
            if namespace:
                namespaces.add(namespace)
        # Augment with the Iceberg catalog's live namespace list when
        # the catalog wrapper is reachable.
        try:
            from aqp.data.iceberg_catalog import list_namespaces

            for ns in list_namespaces() or []:
                if isinstance(ns, str):
                    namespaces.add(ns)
                elif isinstance(ns, (list, tuple)) and ns:
                    namespaces.add(str(ns[0]))
        except Exception:  # noqa: BLE001
            pass
        self.cache.delete(zkey)
        if not namespaces:
            return 0
        self.cache.zadd(zkey, {ns: 0.0 for ns in sorted(namespaces)})
        self.cache.expire(zkey, settings.cache_master_ttl_s)
        self.cache.set_string(category_stamp("namespaces"), datetime.utcnow().isoformat())
        return len(namespaces)

    def _populate_sink_kinds(self, _session: Session) -> int:
        zkey = names_zset("sink_kinds")
        kinds: set[str] = set()
        try:
            from aqp.data.fetchers.sinks import SINK_KINDS

            for descriptor in SINK_KINDS:
                kind = getattr(descriptor, "kind", None) or getattr(descriptor, "name", None)
                if kind:
                    kinds.add(str(kind))
        except Exception:  # noqa: BLE001
            pass
        if not kinds:
            kinds = {"iceberg", "parquet", "kafka"}
        self.cache.delete(zkey)
        self.cache.zadd(zkey, {k: 0.0 for k in sorted(kinds)})
        for kind in sorted(kinds):
            id_key = by_id_hash("sink_kinds", kind)
            self.cache.hset(id_key, {"kind": kind})
            self.cache.expire(id_key, settings.cache_master_ttl_s)
        self.cache.expire(zkey, settings.cache_master_ttl_s)
        self.cache.set_string(category_stamp("sink_kinds"), datetime.utcnow().isoformat())
        return len(kinds)

    def _populate_sink_names(self, session: Session) -> int:
        try:
            from aqp.persistence.models_sinks import SinkRow
        except Exception:  # noqa: BLE001
            return 0
        try:
            rows = session.execute(
                select(SinkRow).where(SinkRow.enabled.is_(True))
            ).scalars().all()
        except SQLAlchemyError:
            return 0
        zkey = names_zset("sink_names")
        self.cache.delete(zkey)
        if not rows:
            return 0
        self.cache.zadd(zkey, {str(r.name): 0.0 for r in rows})
        for row in rows:
            id_key = by_id_hash("sink_names", str(row.id))
            self.cache.hset(
                id_key,
                {
                    "id": str(row.id),
                    "name": str(row.name),
                    "kind": str(row.kind),
                    "enabled": "true" if row.enabled else "false",
                },
            )
            self.cache.expire(id_key, settings.cache_instance_ttl_s)
        self.cache.expire(zkey, settings.cache_instance_ttl_s)
        self.cache.set_string(category_stamp("sink_names"), datetime.utcnow().isoformat())
        return len(rows)

    def _populate_airbyte_connectors(self, session: Session) -> int:
        zkey = names_zset("airbyte_connectors")
        connectors: dict[str, dict[str, Any]] = {}
        # Curated catalog (always available)
        try:
            from aqp.data.airbyte import list_connectors

            for connector in list_connectors():
                cid = str(getattr(connector, "id", "") or "")
                if not cid:
                    continue
                connectors[cid] = {
                    "id": cid,
                    "name": str(getattr(connector, "name", cid) or cid),
                    "kind": str(getattr(connector, "kind", "source") or "source"),
                    "runtime": str(getattr(connector, "runtime", "hybrid") or "hybrid"),
                    "tags": getattr(connector, "tags", []) or [],
                }
        except Exception:  # noqa: BLE001
            pass
        # Project-scoped persisted rows
        try:
            from aqp.persistence.models_airbyte import AirbyteConnectorRow

            try:
                rows = session.execute(select(AirbyteConnectorRow)).scalars().all()
            except SQLAlchemyError:
                rows = []
            for row in rows:
                cid = str(row.connector_id)
                connectors[cid] = {
                    "id": cid,
                    "name": str(row.name or cid),
                    "kind": str(row.kind or "source"),
                    "runtime": str(row.runtime or "hybrid"),
                    "row_id": str(row.id),
                }
        except Exception:  # noqa: BLE001
            pass
        self.cache.delete(zkey)
        if not connectors:
            return 0
        self.cache.zadd(zkey, {cid: 0.0 for cid in sorted(connectors)})
        for cid, payload in connectors.items():
            id_key = by_id_hash("airbyte_connectors", cid)
            self.cache.hset(id_key, payload)
            self.cache.expire(id_key, settings.cache_instance_ttl_s)
        self.cache.expire(zkey, settings.cache_instance_ttl_s)
        self.cache.set_string(category_stamp("airbyte_connectors"), datetime.utcnow().isoformat())
        return len(connectors)

    def _populate_projects(self, session: Session) -> int:
        try:
            from aqp.persistence.models_tenancy import Project
        except Exception:  # noqa: BLE001
            return 0
        try:
            rows = session.execute(select(Project)).scalars().all()
        except SQLAlchemyError:
            return 0
        zkey = names_zset("projects")
        self.cache.delete(zkey)
        if not rows:
            return 0
        mapping: dict[str, float] = {}
        for row in rows:
            name = str(getattr(row, "name", "") or "")
            if not name:
                continue
            mapping[name] = 0.0
            id_key = by_id_hash("projects", str(row.id))
            self.cache.hset(
                id_key,
                {
                    "id": str(row.id),
                    "name": name,
                    "workspace_id": str(getattr(row, "workspace_id", "") or ""),
                },
            )
            self.cache.expire(id_key, settings.cache_master_ttl_s)
        if mapping:
            self.cache.zadd(zkey, mapping)
        self.cache.expire(zkey, settings.cache_master_ttl_s)
        self.cache.set_string(category_stamp("projects"), datetime.utcnow().isoformat())
        return len(rows)

    def _populate_credentials(self, _session: Session) -> int:
        zkey = names_zset("credentials")
        names: list[str] = []
        try:
            from aqp.credentials.resolver import get_resolver

            resolver = get_resolver()
            iter_known = getattr(resolver, "iter_known_keys", None)
            if callable(iter_known):
                names = sorted({str(k) for k in iter_known() if k})
        except Exception:  # noqa: BLE001
            pass
        self.cache.delete(zkey)
        if not names:
            return 0
        self.cache.zadd(zkey, {n: 0.0 for n in names})
        for name in names:
            id_key = by_id_hash("credentials", name)
            self.cache.hset(id_key, {"name": name})
            self.cache.expire(id_key, settings.cache_instance_ttl_s)
        self.cache.expire(zkey, settings.cache_instance_ttl_s)
        self.cache.set_string(category_stamp("credentials"), datetime.utcnow().isoformat())
        return len(names)


def _dataset_payload(row: Any) -> dict[str, Any]:
    """Project a :class:`DatasetCatalog` row into a hash payload."""
    return {
        "id": str(getattr(row, "id", "") or ""),
        "name": str(getattr(row, "name", "") or ""),
        "provider": str(getattr(row, "provider", "") or ""),
        "domain": str(getattr(row, "domain", "") or ""),
        "iceberg_identifier": str(getattr(row, "iceberg_identifier", "") or ""),
        "load_mode": str(getattr(row, "load_mode", "") or ""),
        "medallion_layer": str(getattr(row, "medallion_layer", "") or ""),
        "dataset_kind": str(getattr(row, "dataset_kind", "") or ""),
        "is_ingested": "true" if bool(getattr(row, "is_ingested", False)) else "false",
        "spec_hash": str(getattr(row, "spec_hash", "") or ""),
        "tags": getattr(row, "tags", []) or [],
    }


__all__ = ["MetadataPrefetcher"]
