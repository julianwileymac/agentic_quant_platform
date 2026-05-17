"""CFPB Consumer Complaint Database adapter implementing :class:`DataSourceAdapter`.

Pulls incremental complaints by company / product / date window, lands
them as one logical Iceberg table per ingestion (``aqp_cfpb.complaints``)
via :func:`aqp.data.iceberg_catalog.append_arrow`, mirrors curated
fields into Postgres for fast queries, and registers lineage in the
dataset catalog.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd
import pyarrow as pa

from aqp.config import settings
from aqp.data.catalog import register_dataset_version
from aqp.data.iceberg_catalog import append_arrow, ensure_namespace
from aqp.data.sources.base import (
    DataSourceAdapter,
    IdentifierSpec,
    ObservationsResult,
    ProbeResult,
)
from aqp.data.sources.cfpb.catalog import upsert_cfpb_complaint
from aqp.data.sources.cfpb.client import CfpbClient
from aqp.data.sources.domains import DataDomain
from aqp.data.sources.resolvers.identifiers import IdentifierResolver

logger = logging.getLogger(__name__)


CFPB_NAMESPACE = "aqp_cfpb"
CFPB_TABLE = "complaints"
CFPB_COLUMNS = [
    "complaint_id",
    "company",
    "company_response_to_consumer",
    "consumer_complaint_narrative",
    "consumer_consent_provided",
    "date_received",
    "date_sent_to_company",
    "issue",
    "sub_issue",
    "product",
    "sub_product",
    "state",
    "zip_code",
    "submitted_via",
    "tags",
    "timely",
    "vt_symbol",
]


class CfpbComplaintsAdapter(DataSourceAdapter):
    """Adapter for CFPB consumer complaints."""

    source_key = "cfpb"
    display_name = "CFPB Consumer Complaint Database"
    domain = DataDomain.REGULATORY_CFPB_COMPLAINT

    def __init__(self, client: CfpbClient | None = None) -> None:
        self.client = client or CfpbClient()

    # ------------------------------------------------------------------ contract
    def probe(self) -> ProbeResult:
        ok, message = self.client.probe()
        return ProbeResult.success(message) if ok else ProbeResult.failure(message)

    def fetch_metadata(self, **kwargs: Any) -> dict[str, Any]:
        try:
            page = self.client.search_page(size=1, frm=0)
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "error": str(exc)}
        total = (page.get("hits") or {}).get("total")
        if isinstance(total, dict):
            total = total.get("value")
        return {
            "available": True,
            "total_records_estimate": int(total or 0),
            "endpoint": self.client.base_url,
        }

    def fetch_observations(
        self,
        *,
        company: str | None = None,
        product: str | None = None,
        date_received_min: str | None = None,
        date_received_max: str | None = None,
        has_narrative: bool | None = None,
        max_records: int | None = 5000,
        vt_symbol: str | None = None,
        persist: bool = True,
        emit_lineage: bool = True,
    ) -> ObservationsResult:
        rows: list[dict[str, Any]] = []
        for hit in self.client.iter_complaints(
            company=company,
            product=product,
            date_received_min=date_received_min,
            date_received_max=date_received_max,
            has_narrative=has_narrative,
            max_records=max_records,
        ):
            row = {col: hit.get(col) for col in CFPB_COLUMNS if col in hit or col in {"vt_symbol"}}
            row["complaint_id"] = str(hit.get("complaint_id") or "")
            row["company"] = str(hit.get("company") or "").strip()
            if vt_symbol and not row.get("vt_symbol"):
                row["vt_symbol"] = vt_symbol
            rows.append(row)
        if not rows:
            return ObservationsResult(data=pd.DataFrame(columns=CFPB_COLUMNS))
        df = pd.DataFrame(rows, columns=CFPB_COLUMNS).fillna("")
        for col in ("date_received", "date_sent_to_company"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")

        lineage: dict[str, Any] = {}
        identifiers: list[IdentifierSpec] = []
        if persist and not df.empty:
            self._write_iceberg(df)
            for record in df.to_dict(orient="records"):
                upsert_cfpb_complaint(record)
            if emit_lineage:
                lineage = self._register_lineage(df, company=company)
            for company_name in {str(c).strip() for c in df["company"].tolist() if c}:
                identifiers.append(
                    IdentifierSpec(
                        scheme="cfpb_company_name",
                        value=company_name,
                        entity_kind="issuer",
                        meta={"source": "cfpb"},
                    )
                )
            try:
                IdentifierResolver(source_name=self.source_key).upsert_links(
                    identifiers, default_entity_kind="issuer"
                )
            except Exception:  # pragma: no cover
                logger.debug("CFPB identifier upsert failed", exc_info=True)
        return ObservationsResult(data=df, lineage=lineage, identifiers=identifiers)

    def capabilities(self) -> dict[str, Any]:
        return {
            "domain": str(self.domain),
            "source_key": self.source_key,
            "supports_company_filter": True,
            "supports_date_range": True,
            "supports_narrative_filter": True,
        }

    # ------------------------------------------------------------------ internals
    def _write_iceberg(self, df: pd.DataFrame) -> None:
        try:
            ensure_namespace(CFPB_NAMESPACE)
            table = pa.Table.from_pandas(df, preserve_index=False)
            append_arrow(f"{CFPB_NAMESPACE}.{CFPB_TABLE}", table)
        except Exception:  # pragma: no cover - iceberg optional
            logger.debug("CFPB Iceberg write failed", exc_info=True)

    def _register_lineage(
        self,
        df: pd.DataFrame,
        *,
        company: str | None,
    ) -> dict[str, Any]:
        try:
            return register_dataset_version(
                name=f"cfpb.complaints.{company or 'all'}",
                provider="cfpb",
                domain=str(self.domain),
                df=df.assign(timestamp=df["date_received"]).rename(columns={"company": "vt_symbol_alt"}),
                storage_uri=f"iceberg://{CFPB_NAMESPACE}.{CFPB_TABLE}",
                file_count=1,
                meta={
                    "company": company or "",
                    "rows": int(len(df)),
                    "min_date": str(df["date_received"].min()),
                    "max_date": str(df["date_received"].max()),
                },
            )
        except Exception:  # pragma: no cover
            logger.debug("CFPB lineage registration failed", exc_info=True)
            return {}


__all__ = [
    "CFPB_COLUMNS",
    "CfpbComplaintsAdapter",
]
