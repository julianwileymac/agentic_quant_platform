"""USPTO PatentsView granted-patents adapter."""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import pyarrow as pa

from aqp.data.catalog import register_dataset_version
from aqp.data.iceberg_catalog import append_arrow, ensure_namespace
from aqp.data.sources.base import (
    DataSourceAdapter,
    IdentifierSpec,
    ObservationsResult,
    ProbeResult,
)
from aqp.data.sources.domains import DataDomain
from aqp.data.sources.uspto.catalog import upsert_uspto_patent
from aqp.data.sources.uspto.client import UsptoClient

logger = logging.getLogger(__name__)


USPTO_NAMESPACE = "aqp_uspto"
USPTO_PATENTS_TABLE = "patents"


class UsptoPatentsAdapter(DataSourceAdapter):
    """Adapter for USPTO PatentsView granted patents."""

    source_key = "uspto_patents"
    display_name = "USPTO Granted Patents (PatentsView)"
    domain = DataDomain.REGULATORY_USPTO_PATENT

    def __init__(self, client: UsptoClient | None = None) -> None:
        self.client = client or UsptoClient()

    def probe(self) -> ProbeResult:
        ok, message = self.client.probe()
        return ProbeResult.success(message) if ok else ProbeResult.failure(message)

    def fetch_metadata(self, **kwargs: Any) -> dict[str, Any]:
        return {"endpoint": self.client.patentsview_url, "requires_api_key": bool(self.client.api_key)}

    def fetch_observations(
        self,
        *,
        assignee: str | None = None,
        date_min: str | None = None,
        date_max: str | None = None,
        max_records: int | None = 5000,
        vt_symbol: str | None = None,
        persist: bool = True,
        emit_lineage: bool = True,
    ) -> ObservationsResult:
        clauses: list[dict[str, Any]] = []
        if assignee:
            clauses.append({"_text_phrase": {"assignees.assignee_organization": assignee}})
        if date_min:
            clauses.append({"_gte": {"patent_date": date_min}})
        if date_max:
            clauses.append({"_lte": {"patent_date": date_max}})
        query: dict[str, Any] = {"_and": clauses} if clauses else {"_text_any": {"patent_title": "the"}}
        rows: list[dict[str, Any]] = []
        try:
            for hit in self.client.iter_patents(query=query, max_records=max_records):
                if vt_symbol:
                    hit["vt_symbol"] = vt_symbol
                rows.append(hit)
        except Exception:  # noqa: BLE001
            logger.exception("PatentsView iteration failed")
        if not rows:
            return ObservationsResult(data=pd.DataFrame())
        df = pd.json_normalize(rows, max_level=1)
        if persist and not df.empty:
            self._write_iceberg(df)
            for r in rows:
                upsert_uspto_patent(r)
        identifiers: list[IdentifierSpec] = []
        if assignee:
            identifiers.append(
                IdentifierSpec(
                    scheme="uspto_assignee",
                    value=assignee,
                    entity_kind="issuer",
                )
            )
        lineage = (
            self._register_lineage(df, assignee=assignee)
            if (persist and emit_lineage and not df.empty)
            else {}
        )
        return ObservationsResult(data=df, lineage=lineage, identifiers=identifiers)

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
            append_arrow(f"{USPTO_NAMESPACE}.{USPTO_PATENTS_TABLE}", table)
        except Exception:  # pragma: no cover
            logger.debug("USPTO patents Iceberg write failed", exc_info=True)

    def _register_lineage(self, df: pd.DataFrame, *, assignee: str | None) -> dict[str, Any]:
        try:
            return register_dataset_version(
                name=f"uspto.patents.{assignee or 'all'}",
                provider="uspto",
                domain=str(self.domain),
                df=df,
                storage_uri=f"iceberg://{USPTO_NAMESPACE}.{USPTO_PATENTS_TABLE}",
                file_count=1,
                meta={"assignee": assignee or "", "rows": int(len(df))},
            )
        except Exception:  # pragma: no cover
            return {}


__all__ = ["USPTO_NAMESPACE", "USPTO_PATENTS_TABLE", "UsptoPatentsAdapter"]
