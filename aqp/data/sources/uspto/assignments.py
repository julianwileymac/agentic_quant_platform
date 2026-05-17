"""USPTO PEDS patent assignments adapter."""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import pyarrow as pa

from aqp.data.catalog import register_dataset_version
from aqp.data.iceberg_catalog import append_arrow, ensure_namespace
from aqp.data.sources.base import (
    DataSourceAdapter,
    ObservationsResult,
    ProbeResult,
)
from aqp.data.sources.domains import DataDomain
from aqp.data.sources.uspto.catalog import upsert_uspto_assignment
from aqp.data.sources.uspto.client import UsptoClient

logger = logging.getLogger(__name__)


USPTO_NAMESPACE = "aqp_uspto"
USPTO_ASSIGNMENTS_TABLE = "assignments"


class UsptoAssignmentsAdapter(DataSourceAdapter):
    """Adapter for USPTO patent assignments via PEDS."""

    source_key = "uspto_assignments"
    display_name = "USPTO Patent Assignments (PEDS)"
    domain = DataDomain.REGULATORY_USPTO_ASSIGNMENT

    def __init__(self, client: UsptoClient | None = None) -> None:
        self.client = client or UsptoClient()

    def probe(self) -> ProbeResult:
        ok, message = self.client.probe()
        return ProbeResult.success(message) if ok else ProbeResult.failure(message)

    def fetch_metadata(self, **kwargs: Any) -> dict[str, Any]:
        return {"endpoint": self.client.peds_url}

    def fetch_observations(
        self,
        *,
        search_text: str,
        max_records: int | None = 5000,
        vt_symbol: str | None = None,
        persist: bool = True,
        emit_lineage: bool = True,
    ) -> ObservationsResult:
        rows: list[dict[str, Any]] = []
        start = 0
        page_size = 100
        while True:
            try:
                payload = self.client.assignments(searchText=search_text, rows=page_size, start=start)
            except Exception:  # noqa: BLE001
                logger.exception("PEDS request failed")
                break
            results = (
                (payload.get("queryResults") or {})
                .get("searchResponse", {})
                .get("response", {})
                .get("docs")
                or []
            )
            if not results:
                break
            for hit in results:
                if vt_symbol:
                    hit["vt_symbol"] = vt_symbol
                rows.append(hit)
                if max_records is not None and len(rows) >= max_records:
                    break
            if max_records is not None and len(rows) >= max_records:
                break
            if len(results) < page_size:
                break
            start += page_size
        if not rows:
            return ObservationsResult(data=pd.DataFrame())
        df = pd.json_normalize(rows, max_level=1)
        if persist and not df.empty:
            self._write_iceberg(df)
            for r in rows:
                upsert_uspto_assignment(r)
        lineage = self._register_lineage(df, search=search_text) if (persist and emit_lineage and not df.empty) else {}
        return ObservationsResult(data=df, lineage=lineage)

    def capabilities(self) -> dict[str, Any]:
        return {"domain": str(self.domain), "source_key": self.source_key}

    def _write_iceberg(self, df: pd.DataFrame) -> None:
        try:
            ensure_namespace(USPTO_NAMESPACE)
            sanitised = df.copy()
            for col in sanitised.columns:
                if sanitised[col].dtype == object:
                    sanitised[col] = sanitised[col].astype(str)
            table = pa.Table.from_pandas(sanitised, preserve_index=False)
            append_arrow(f"{USPTO_NAMESPACE}.{USPTO_ASSIGNMENTS_TABLE}", table)
        except Exception:  # pragma: no cover
            logger.debug("USPTO assignments Iceberg write failed", exc_info=True)

    def _register_lineage(self, df: pd.DataFrame, *, search: str) -> dict[str, Any]:
        try:
            return register_dataset_version(
                name=f"uspto.assignments.{search}",
                provider="uspto",
                domain=str(self.domain),
                df=df,
                storage_uri=f"iceberg://{USPTO_NAMESPACE}.{USPTO_ASSIGNMENTS_TABLE}",
                file_count=1,
                meta={"search": search, "rows": int(len(df))},
            )
        except Exception:  # pragma: no cover
            return {}


__all__ = ["USPTO_ASSIGNMENTS_TABLE", "USPTO_NAMESPACE", "UsptoAssignmentsAdapter"]
