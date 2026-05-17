"""FDA enforcement recalls (drug + device + food)."""
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
from aqp.data.sources.fda.catalog import upsert_fda_recall
from aqp.data.sources.fda.client import FdaClient

logger = logging.getLogger(__name__)


FDA_RECALL_NAMESPACE = "aqp_fda"
FDA_RECALL_TABLE = "recalls"


class FdaRecallsAdapter(DataSourceAdapter):
    """Adapter for FDA enforcement recalls."""

    source_key = "fda_recalls"
    display_name = "FDA Enforcement Recalls"
    domain = DataDomain.REGULATORY_FDA_RECALL

    def __init__(self, client: FdaClient | None = None) -> None:
        self.client = client or FdaClient()

    def probe(self) -> ProbeResult:
        ok, message = self.client.probe()
        return ProbeResult.success(message) if ok else ProbeResult.failure(message)

    def fetch_metadata(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "endpoints": [
                "drug/enforcement.json",
                "device/enforcement.json",
                "food/enforcement.json",
            ],
        }

    def fetch_observations(
        self,
        *,
        firm: str | None = None,
        classification: str | None = None,
        date_min: str | None = None,
        date_max: str | None = None,
        product_type: str = "drug",  # drug | device | food
        max_records: int | None = 5000,
        vt_symbol: str | None = None,
        persist: bool = True,
        emit_lineage: bool = True,
    ) -> ObservationsResult:
        endpoint = f"{product_type}/enforcement.json"
        clauses: list[str] = []
        if firm:
            clauses.append(f'recalling_firm:"{firm}"')
        if classification:
            clauses.append(f'classification:"{classification}"')
        if date_min and date_max:
            clauses.append(
                f"recall_initiation_date:[{date_min.replace('-', '')} TO {date_max.replace('-', '')}]"
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
                upsert_fda_recall(r, product_type=product_type)
        lineage = (
            self._register_lineage(df, firm=firm, product_type=product_type)
            if (persist and emit_lineage and not df.empty)
            else {}
        )
        return ObservationsResult(data=df, lineage=lineage)

    def capabilities(self) -> dict[str, Any]:
        return {
            "domain": str(self.domain),
            "source_key": self.source_key,
            "endpoints": [
                "drug/enforcement.json",
                "device/enforcement.json",
                "food/enforcement.json",
            ],
        }

    def _write_iceberg(self, df: pd.DataFrame) -> None:
        try:
            ensure_namespace(FDA_RECALL_NAMESPACE)
            sanitised = df.copy()
            for col in sanitised.columns:
                if sanitised[col].dtype == object:
                    sanitised[col] = sanitised[col].astype(str)
            table = pa.Table.from_pandas(sanitised, preserve_index=False)
            append_arrow(f"{FDA_RECALL_NAMESPACE}.{FDA_RECALL_TABLE}", table)
        except Exception:  # pragma: no cover
            logger.debug("FDA recall Iceberg write failed", exc_info=True)

    def _register_lineage(self, df: pd.DataFrame, *, firm: str | None, product_type: str) -> dict[str, Any]:
        try:
            return register_dataset_version(
                name=f"fda.recalls.{product_type}.{firm or 'all'}",
                provider="fda",
                domain=str(self.domain),
                df=df,
                storage_uri=f"iceberg://{FDA_RECALL_NAMESPACE}.{FDA_RECALL_TABLE}",
                file_count=1,
                meta={"firm": firm or "", "product_type": product_type, "rows": int(len(df))},
            )
        except Exception:  # pragma: no cover
            return {}


__all__ = ["FDA_RECALL_NAMESPACE", "FDA_RECALL_TABLE", "FdaRecallsAdapter"]
