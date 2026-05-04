"""Unified metadata catalog read model backed by PostgreSQL plus Iceberg."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import and_, desc, func, or_, select

from aqp.data import iceberg_catalog
from aqp.persistence.db import get_session
from aqp.persistence.models import DataLink, DatasetCatalog, DatasetVersion, Instrument

logger = logging.getLogger(__name__)


def _escaped_like_prefix(column: Any, namespace: str) -> Any:
    """``LIKE`` prefix match where ``namespace`` may contain ``_`` (SQL wildcard)."""
    esc = namespace.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.like(f"{esc}.%", escape="\\")


@dataclass(frozen=True)
class MetadataDataset:
    id: str
    name: str
    provider: str
    domain: str
    namespace: str | None = None
    table: str | None = None
    iceberg_identifier: str | None = None
    storage_uri: str | None = None
    source_uri: str | None = None
    frequency: str | None = None
    load_mode: str = "registered"
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    latest_version: int | None = None
    latest_dataset_hash: str | None = None
    latest_row_count: int | None = None
    latest_symbol_count: int | None = None
    latest_file_count: int | None = None
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    entity_link_count: int = 0
    data_link_count: int = 0
    streaming_link_count: int = 0
    has_annotation: bool = False
    updated_at: datetime | None = None
    created_at: datetime | None = None
    entry_kind: Literal["dataset", "instrument"] = "dataset"
    vt_symbol: str | None = None
    ticker: str | None = None
    exchange: str | None = None
    asset_class: str | None = None
    security_type: str | None = None
    sector: str | None = None
    industry: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "domain": self.domain,
            "namespace": self.namespace,
            "table": self.table,
            "iceberg_identifier": self.iceberg_identifier,
            "storage_uri": self.storage_uri,
            "source_uri": self.source_uri,
            "frequency": self.frequency,
            "load_mode": self.load_mode,
            "description": self.description,
            "tags": self.tags,
            "latest_version": self.latest_version,
            "latest_dataset_hash": self.latest_dataset_hash,
            "latest_row_count": self.latest_row_count,
            "latest_symbol_count": self.latest_symbol_count,
            "latest_file_count": self.latest_file_count,
            "coverage_start": self.coverage_start,
            "coverage_end": self.coverage_end,
            "entity_link_count": self.entity_link_count,
            "data_link_count": self.data_link_count,
            "streaming_link_count": self.streaming_link_count,
            "has_annotation": self.has_annotation,
            "updated_at": self.updated_at,
            "created_at": self.created_at,
            "entry_kind": self.entry_kind,
            "vt_symbol": self.vt_symbol,
            "ticker": self.ticker,
            "exchange": self.exchange,
            "asset_class": self.asset_class,
            "security_type": self.security_type,
            "sector": self.sector,
            "industry": self.industry,
        }


class MetadataCatalogService:
    """Compose catalog, lineage, entity, and Iceberg state into one index."""

    @staticmethod
    def _instrument_query_filter(stmt: Any, query: str | None) -> Any:
        q = (query or "").strip()
        if not q:
            return stmt
        needle = f"%{q}%"
        return stmt.where(
            (Instrument.ticker.ilike(needle))
            | (Instrument.vt_symbol.ilike(needle))
            | (Instrument.sector.ilike(needle))
            | (Instrument.industry.ilike(needle))
        )

    def _instrument_metadata_rows(self, *, query: str | None, limit: int) -> list[MetadataDataset]:
        cap = max(1, int(limit))
        payloads: list[dict[str, Any]] = []
        with get_session() as session:
            stmt = self._instrument_query_filter(select(Instrument), query)
            rows = session.execute(
                stmt.order_by(Instrument.ticker.asc()).limit(cap)
            ).scalars().all()
            for row in rows:
                payloads.append(
                    {
                        "id": row.id,
                        "ticker": row.ticker,
                        "vt_symbol": row.vt_symbol,
                        "exchange": row.exchange,
                        "asset_class": row.asset_class,
                        "security_type": row.security_type,
                        "sector": row.sector,
                        "industry": row.industry,
                        "is_active": row.is_active,
                        "updated_at": row.updated_at,
                        "created_at": row.created_at,
                    }
                )
        out: list[MetadataDataset] = []
        for p in payloads:
            parts = [x for x in (p.get("sector"), p.get("industry")) if x]
            desc = " / ".join(parts) if parts else None
            out.append(
                MetadataDataset(
                    id=str(p["id"]),
                    name=str(p["ticker"] or p["vt_symbol"]),
                    provider="instrument",
                    domain="security.master",
                    namespace=str(p["exchange"] or ""),
                    table=str(p["vt_symbol"]),
                    load_mode="active" if p.get("is_active") else "inactive",
                    description=desc,
                    tags=["universe", "instrument"],
                    updated_at=p.get("updated_at"),
                    created_at=p.get("created_at"),
                    entry_kind="instrument",
                    vt_symbol=str(p["vt_symbol"]),
                    ticker=str(p["ticker"]) if p.get("ticker") else None,
                    exchange=str(p["exchange"]) if p.get("exchange") else None,
                    asset_class=str(p["asset_class"]) if p.get("asset_class") else None,
                    security_type=str(p["security_type"]) if p.get("security_type") else None,
                    sector=str(p["sector"]) if p.get("sector") else None,
                    industry=str(p["industry"]) if p.get("industry") else None,
                )
            )
        return out

    def list_datasets(
        self,
        *,
        query: str | None = None,
        provider: str | None = None,
        domain: str | None = None,
        namespace: str | None = None,
        include_iceberg_only: bool = True,
        limit: int = 250,
    ) -> list[dict[str, Any]]:
        cap = max(1, int(limit))
        if namespace == "__universe__":
            return [r.to_dict() for r in self._instrument_metadata_rows(query=query, limit=cap)]
        rows = self._catalog_rows(
            query=query,
            provider=provider,
            domain=domain,
            namespace=namespace,
            limit=cap,
        )
        out = [row.to_dict() for row in rows]
        if namespace == "__registered__":
            # Registered-only view is Postgres catalog rows without Iceberg ids.
            # Do not append Iceberg-discovered tables (would desync the sidebar filter).
            return out[:cap]
        if include_iceberg_only:
            existing = {row["iceberg_identifier"] for row in out if row.get("iceberg_identifier")}
            out.extend(self._iceberg_only_rows(existing, namespace=namespace))
        if not namespace or namespace == "__all__":
            # Prefer recently updated catalog entries when merging with discovered Iceberg tables.
            def _sort_key(row: dict[str, Any]) -> tuple[int, str]:
                ts = row.get("updated_at")
                if ts is None:
                    return (0, "")
                try:
                    stamp = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                except Exception:  # noqa: BLE001
                    stamp = str(ts)
                return (1, stamp)

            out.sort(key=_sort_key, reverse=True)
        return out[:cap]

    def get_dataset(self, dataset_id: str) -> dict[str, Any] | None:
        with get_session() as session:
            row = session.execute(
                select(DatasetCatalog).where(DatasetCatalog.id == dataset_id).limit(1)
            ).scalar_one_or_none()
            if row is None:
                row = session.execute(
                    select(DatasetCatalog)
                    .where(DatasetCatalog.iceberg_identifier == dataset_id)
                    .limit(1)
                ).scalar_one_or_none()
            if row is None:
                return None
            return self._row_to_dataset(session, row).to_dict()

    def lineage(self, dataset_id: str, *, limit: int = 250) -> dict[str, Any]:
        dataset = self.get_dataset(dataset_id)
        if dataset is None:
            return {"dataset": None, "nodes": [], "edges": []}
        nodes: list[dict[str, Any]] = [
            {
                "id": dataset["id"],
                "kind": "dataset",
                "label": dataset["name"],
                "meta": dataset,
            }
        ]
        edges: list[dict[str, Any]] = []
        with get_session() as session:
            version_ids = [
                row[0]
                for row in session.execute(
                    select(DatasetVersion.id)
                    .where(DatasetVersion.catalog_id == dataset["id"])
                    .order_by(desc(DatasetVersion.version))
                    .limit(max(1, int(limit)))
                ).all()
            ]
            if version_ids:
                data_links = session.execute(
                    select(DataLink)
                    .where(DataLink.dataset_version_id.in_(version_ids))
                    .limit(max(1, int(limit)))
                ).scalars().all()
                for link in data_links:
                    node_id = link.instrument_id or f"{link.entity_kind}:{link.entity_id}"
                    nodes.append(
                        {
                            "id": node_id,
                            "kind": link.entity_kind,
                            "label": link.entity_id,
                            "meta": {
                                "coverage_start": link.coverage_start,
                                "coverage_end": link.coverage_end,
                                "row_count": link.row_count,
                            },
                        }
                    )
                    edges.append(
                        {
                            "source": dataset["id"],
                            "target": node_id,
                            "kind": "covers",
                        }
                    )
            for item in self._streaming_links(session, str(dataset["id"]), limit=limit):
                node_id = f"{item['kind']}:{item['target_ref']}"
                nodes.append({"id": node_id, "kind": item["kind"], "label": item["target_ref"], "meta": item})
                direction = item.get("direction") or "source"
                source, target = (node_id, dataset["id"]) if direction == "source" else (dataset["id"], node_id)
                edges.append({"source": source, "target": target, "kind": direction})
        return {"dataset": dataset, "nodes": nodes, "edges": edges}

    def health(self) -> dict[str, Any]:
        db_ok = False
        db_error = None
        try:
            with get_session() as session:
                session.execute(select(func.count()).select_from(DatasetCatalog)).scalar_one()
                db_ok = True
        except Exception as exc:  # noqa: BLE001
            db_error = str(exc)
        iceberg = iceberg_catalog.health_check()
        return {
            "postgres": {"ok": db_ok, "error": db_error},
            "iceberg": iceberg,
            "ok": db_ok and bool(iceberg.get("ok", False)),
        }

    def _catalog_namespace_sql(self, namespace: str | None) -> Any | None:
        """SQL predicate matching the UI namespace sidebar (Iceberg ns or registered provider)."""
        if not namespace or namespace == "__all__":
            return None
        if namespace == "__registered__":
            return DatasetCatalog.iceberg_identifier.is_(None)
        return or_(
            DatasetCatalog.iceberg_identifier == namespace,
            _escaped_like_prefix(DatasetCatalog.iceberg_identifier, namespace),
            and_(DatasetCatalog.iceberg_identifier.is_(None), DatasetCatalog.provider == namespace),
        )

    def _catalog_rows(
        self,
        *,
        query: str | None,
        provider: str | None,
        domain: str | None,
        namespace: str | None,
        limit: int,
    ) -> list[MetadataDataset]:
        with get_session() as session:
            stmt = select(DatasetCatalog)
            if provider:
                stmt = stmt.where(DatasetCatalog.provider == provider)
            if domain:
                stmt = stmt.where(DatasetCatalog.domain.ilike(f"{domain}%"))
            if query:
                needle = f"%{query}%"
                stmt = stmt.where(
                    (DatasetCatalog.name.ilike(needle))
                    | (DatasetCatalog.provider.ilike(needle))
                    | (DatasetCatalog.domain.ilike(needle))
                    | (DatasetCatalog.iceberg_identifier.ilike(needle))
                )
            ns_clause = self._catalog_namespace_sql(namespace)
            if ns_clause is not None:
                stmt = stmt.where(ns_clause)
            rows = session.execute(
                stmt.order_by(desc(DatasetCatalog.updated_at)).limit(max(1, int(limit)))
            ).scalars().all()
            return [self._row_to_dataset(session, row) for row in rows]

    def _row_to_dataset(self, session: Any, row: DatasetCatalog) -> MetadataDataset:
        latest = session.execute(
            select(DatasetVersion)
            .where(DatasetVersion.catalog_id == row.id)
            .order_by(desc(DatasetVersion.version))
            .limit(1)
        ).scalar_one_or_none()
        version_ids = [
            item[0]
            for item in session.execute(
                select(DatasetVersion.id).where(DatasetVersion.catalog_id == row.id)
            ).all()
        ]
        data_link_count = 0
        coverage_start = coverage_end = None
        if version_ids:
            coverage = session.execute(
                select(
                    func.count(DataLink.id),
                    func.min(DataLink.coverage_start),
                    func.max(DataLink.coverage_end),
                ).where(DataLink.dataset_version_id.in_(version_ids))
            ).one()
            data_link_count = int(coverage[0] or 0)
            coverage_start = coverage[1]
            coverage_end = coverage[2]
        ns, table = self._split_identifier(row.iceberg_identifier)
        return MetadataDataset(
            id=row.id,
            name=row.name,
            provider=row.provider,
            domain=row.domain,
            namespace=ns or row.provider,
            table=table or row.name,
            iceberg_identifier=row.iceberg_identifier,
            storage_uri=row.storage_uri,
            source_uri=row.source_uri,
            frequency=row.frequency,
            load_mode=row.load_mode or "registered",
            description=row.description or (row.llm_annotations or {}).get("description"),
            tags=list(row.tags or []),
            latest_version=latest.version if latest else None,
            latest_dataset_hash=latest.dataset_hash if latest else None,
            latest_row_count=latest.row_count if latest else None,
            latest_symbol_count=latest.symbol_count if latest else None,
            latest_file_count=latest.file_count if latest else None,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            entity_link_count=self._entity_link_count(session, row.id),
            data_link_count=data_link_count,
            streaming_link_count=self._streaming_link_count(session, row.id),
            has_annotation=bool(row.llm_annotations),
            updated_at=row.updated_at,
            created_at=row.created_at,
        )

    def _iceberg_only_rows(self, existing: set[str], *, namespace: str | None) -> list[dict[str, Any]]:
        if namespace == "__registered__":
            return []
        try:
            identifiers = iceberg_catalog.list_tables(
                None if not namespace or namespace == "__all__" else namespace
            )
        except Exception:
            logger.debug("Iceberg table listing unavailable for metadata catalog", exc_info=True)
            return []
        out: list[dict[str, Any]] = []
        for identifier in identifiers:
            if identifier in existing:
                continue
            ns, table = self._split_identifier(identifier)
            out.append(
                MetadataDataset(
                    id=identifier,
                    name=table or identifier,
                    provider="iceberg",
                    domain="iceberg.table",
                    namespace=ns,
                    table=table,
                    iceberg_identifier=identifier,
                    load_mode="discovered",
                ).to_dict()
            )
        return out

    @staticmethod
    def _split_identifier(identifier: str | None) -> tuple[str | None, str | None]:
        if not identifier or "." not in identifier:
            return None, None
        ns, _, table = identifier.rpartition(".")
        return ns or None, table or None

    @staticmethod
    def _entity_link_count(session: Any, catalog_id: str) -> int:
        try:
            from aqp.persistence.models_entity_registry import EntityDatasetLink

            return int(
                session.execute(
                    select(func.count()).select_from(EntityDatasetLink).where(
                        EntityDatasetLink.dataset_catalog_id == catalog_id
                    )
                ).scalar_one()
                or 0
            )
        except Exception:
            return 0

    @staticmethod
    def _streaming_link_count(session: Any, catalog_id: str) -> int:
        try:
            from aqp.persistence.models_streaming_links import StreamingDatasetLink

            return int(
                session.execute(
                    select(func.count()).select_from(StreamingDatasetLink).where(
                        StreamingDatasetLink.dataset_catalog_id == catalog_id
                    )
                ).scalar_one()
                or 0
            )
        except Exception:
            return 0

    @staticmethod
    def _streaming_links(session: Any, catalog_id: str, *, limit: int) -> list[dict[str, Any]]:
        try:
            from aqp.persistence.models_streaming_links import StreamingDatasetLink

            rows = session.execute(
                select(StreamingDatasetLink)
                .where(StreamingDatasetLink.dataset_catalog_id == catalog_id)
                .limit(max(1, int(limit)))
            ).scalars().all()
            return [
                {
                    "id": row.id,
                    "kind": row.kind,
                    "target_ref": row.target_ref,
                    "direction": row.direction,
                    "cluster_ref": row.cluster_ref,
                    "enabled": row.enabled,
                }
                for row in rows
            ]
        except Exception:
            return []
