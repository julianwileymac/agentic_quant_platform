"""FDA drug + device applications adapter."""
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
from aqp.data.sources.fda.catalog import upsert_fda_application
from aqp.data.sources.fda.client import FdaClient

logger = logging.getLogger(__name__)


FDA_APP_NAMESPACE = "aqp_fda"
FDA_APP_TABLE = "applications"


class FdaApplicationsAdapter(DataSourceAdapter):
    """Adapter for FDA drug + device applications."""

    source_key = "fda_applications"
    display_name = "FDA Drug + Device Applications"
    domain = DataDomain.REGULATORY_FDA_APPLICATION

    def __init__(self, client: FdaClient | None = None) -> None:
        self.client = client or FdaClient()

    def probe(self) -> ProbeResult:
        ok, message = self.client.probe()
        return ProbeResult.success(message) if ok else ProbeResult.failure(message)

    def fetch_metadata(self, **kwargs: Any) -> dict[str, Any]:
        try:
            page = self.client.search("drug/drugsfda.json", limit=1)
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "error": str(exc)}
        return {
            "available": True,
            "endpoints": ["drug/drugsfda.json", "device/510k.json", "device/pma.json"],
            "metadata": page.get("meta") or {},
        }

    def fetch_observations(
        self,
        *,
        sponsor: str | None = None,
        date_min: str | None = None,
        date_max: str | None = None,
        endpoint: str = "drug/drugsfda.json",
        max_records: int | None = 5000,
        vt_symbol: str | None = None,
        persist: bool = True,
        emit_lineage: bool = True,
    ) -> ObservationsResult:
        clauses: list[str] = []
        if sponsor:
            clauses.append(f'sponsor_name:"{sponsor}"')
        if date_min and date_max:
            clauses.append(
                f"submissions.submission_status_date:[{date_min.replace('-', '')} TO {date_max.replace('-', '')}]"
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
            for r in rows:
                upsert_fda_application(r)
        identifiers: list[IdentifierSpec] = []
        if sponsor:
            identifiers.append(
                IdentifierSpec(
                    scheme="fda_sponsor_name",
                    value=sponsor,
                    entity_kind="issuer",
                )
            )
        lineage = self._register_lineage(df, sponsor=sponsor) if (persist and emit_lineage and not df.empty) else {}
        return ObservationsResult(data=df, lineage=lineage, identifiers=identifiers)

    def capabilities(self) -> dict[str, Any]:
        return {
            "domain": str(self.domain),
            "source_key": self.source_key,
            "endpoints": ["drug/drugsfda.json", "device/510k.json", "device/pma.json"],
        }

    def _write_iceberg(self, df: pd.DataFrame) -> None:
        try:
            ensure_namespace(FDA_APP_NAMESPACE)
            sanitised = df.copy()
            for col in sanitised.columns:
                if sanitised[col].dtype == object:
                    sanitised[col] = sanitised[col].astype(str)
            table = pa.Table.from_pandas(sanitised, preserve_index=False)
            append_arrow(f"{FDA_APP_NAMESPACE}.{FDA_APP_TABLE}", table)
        except Exception:  # pragma: no cover
            logger.debug("FDA app Iceberg write failed", exc_info=True)

    def _register_lineage(self, df: pd.DataFrame, *, sponsor: str | None) -> dict[str, Any]:
        try:
            return register_dataset_version(
                name=f"fda.applications.{sponsor or 'all'}",
                provider="fda",
                domain=str(self.domain),
                df=df,
                storage_uri=f"iceberg://{FDA_APP_NAMESPACE}.{FDA_APP_TABLE}",
                file_count=1,
                meta={"sponsor": sponsor or "", "rows": int(len(df))},
            )
        except Exception:  # pragma: no cover
            return {}


__all__ = ["FDA_APP_NAMESPACE", "FDA_APP_TABLE", "FdaApplicationsAdapter"]
