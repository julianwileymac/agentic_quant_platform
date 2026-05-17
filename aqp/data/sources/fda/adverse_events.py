"""FDA adverse-event adapter (FAERS for drugs, MAUDE for devices)."""
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
from aqp.data.sources.fda.catalog import upsert_fda_adverse_event
from aqp.data.sources.fda.client import FdaClient

logger = logging.getLogger(__name__)


FDA_AE_NAMESPACE = "aqp_fda"
FDA_AE_TABLE = "adverse_events"


class FdaAdverseEventsAdapter(DataSourceAdapter):
    """Adapter for FDA adverse events (FAERS + MAUDE)."""

    source_key = "fda_adverse_events"
    display_name = "FDA Adverse Events (FAERS / MAUDE)"
    domain = DataDomain.REGULATORY_FDA_ADVERSE_EVENT

    def __init__(self, client: FdaClient | None = None) -> None:
        self.client = client or FdaClient()

    def probe(self) -> ProbeResult:
        ok, message = self.client.probe()
        return ProbeResult.success(message) if ok else ProbeResult.failure(message)

    def fetch_metadata(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "endpoints": ["drug/event.json (FAERS)", "device/event.json (MAUDE)"],
        }

    def fetch_observations(
        self,
        *,
        manufacturer: str | None = None,
        product: str | None = None,
        date_min: str | None = None,
        date_max: str | None = None,
        endpoint: str = "drug/event.json",
        max_records: int | None = 5000,
        vt_symbol: str | None = None,
        persist: bool = True,
        emit_lineage: bool = True,
    ) -> ObservationsResult:
        clauses: list[str] = []
        if manufacturer:
            clauses.append(
                f'patient.drug.openfda.manufacturer_name:"{manufacturer}"'
                if "drug" in endpoint
                else f'manufacturer_d_name:"{manufacturer}"'
            )
        if product:
            clauses.append(
                f'patient.drug.medicinalproduct:"{product}"'
                if "drug" in endpoint
                else f'device.brand_name:"{product}"'
            )
        if date_min and date_max:
            clauses.append(
                f"receivedate:[{date_min.replace('-', '')} TO {date_max.replace('-', '')}]"
            )
        search = " AND ".join(clauses) if clauses else None
        rows: list[dict[str, Any]] = []
        for hit in self.client.iter_results(endpoint, search=search, max_records=max_records):
            if vt_symbol:
                hit["vt_symbol"] = vt_symbol
            rows.append(hit)
        if not rows:
            return ObservationsResult(data=pd.DataFrame())
        df = pd.json_normalize(rows, max_level=1)
        if persist and not df.empty:
            self._write_iceberg(df)
            source = "faers" if "drug" in endpoint else "maude"
            for r in rows:
                upsert_fda_adverse_event(r, source=source)
        lineage = (
            self._register_lineage(df, manufacturer=manufacturer, product=product)
            if (persist and emit_lineage and not df.empty)
            else {}
        )
        return ObservationsResult(data=df, lineage=lineage)

    def capabilities(self) -> dict[str, Any]:
        return {
            "domain": str(self.domain),
            "source_key": self.source_key,
            "endpoints": ["drug/event.json", "device/event.json"],
        }

    def _write_iceberg(self, df: pd.DataFrame) -> None:
        try:
            ensure_namespace(FDA_AE_NAMESPACE)
            sanitised = df.copy()
            for col in sanitised.columns:
                if sanitised[col].dtype == object:
                    sanitised[col] = sanitised[col].astype(str)
            table = pa.Table.from_pandas(sanitised, preserve_index=False)
            append_arrow(f"{FDA_AE_NAMESPACE}.{FDA_AE_TABLE}", table)
        except Exception:  # pragma: no cover
            logger.debug("FDA AE Iceberg write failed", exc_info=True)

    def _register_lineage(
        self,
        df: pd.DataFrame,
        *,
        manufacturer: str | None,
        product: str | None,
    ) -> dict[str, Any]:
        try:
            return register_dataset_version(
                name=f"fda.adverse_events.{manufacturer or product or 'all'}",
                provider="fda",
                domain=str(self.domain),
                df=df,
                storage_uri=f"iceberg://{FDA_AE_NAMESPACE}.{FDA_AE_TABLE}",
                file_count=1,
                meta={
                    "manufacturer": manufacturer or "",
                    "product": product or "",
                    "rows": int(len(df)),
                },
            )
        except Exception:  # pragma: no cover
            return {}


__all__ = ["FDA_AE_NAMESPACE", "FDA_AE_TABLE", "FdaAdverseEventsAdapter"]
