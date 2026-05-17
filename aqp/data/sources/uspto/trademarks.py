"""USPTO TSDR trademark adapter."""
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
from aqp.data.sources.uspto.catalog import upsert_uspto_trademark
from aqp.data.sources.uspto.client import UsptoClient

logger = logging.getLogger(__name__)


USPTO_NAMESPACE = "aqp_uspto"
USPTO_TRADEMARKS_TABLE = "trademarks"


class UsptoTrademarksAdapter(DataSourceAdapter):
    """Adapter for USPTO trademark case status (TSDR)."""

    source_key = "uspto_trademarks"
    display_name = "USPTO Trademarks (TSDR)"
    domain = DataDomain.REGULATORY_USPTO_TRADEMARK

    def __init__(self, client: UsptoClient | None = None) -> None:
        self.client = client or UsptoClient()

    def probe(self) -> ProbeResult:
        ok, message = self.client.probe()
        return ProbeResult.success(message) if ok else ProbeResult.failure(message)

    def fetch_metadata(self, **kwargs: Any) -> dict[str, Any]:
        return {"endpoint": self.client.tsdr_url}

    def fetch_observations(
        self,
        *,
        serial_numbers: list[str] | None = None,
        vt_symbol: str | None = None,
        persist: bool = True,
        emit_lineage: bool = True,
    ) -> ObservationsResult:
        if not serial_numbers:
            return ObservationsResult(data=pd.DataFrame())
        rows: list[dict[str, Any]] = []
        for sn in serial_numbers:
            try:
                payload = self.client.trademark_case_status(serial_number=sn)
            except Exception:  # noqa: BLE001
                logger.debug("TSDR fetch failed for %s", sn, exc_info=True)
                continue
            payload["serial_number"] = sn
            if vt_symbol:
                payload["vt_symbol"] = vt_symbol
            rows.append(payload)
        if not rows:
            return ObservationsResult(data=pd.DataFrame())
        df = pd.json_normalize(rows, max_level=2)
        if persist and not df.empty:
            self._write_iceberg(df)
            for r in rows:
                upsert_uspto_trademark(r)
        lineage = self._register_lineage(df) if (persist and emit_lineage and not df.empty) else {}
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
            append_arrow(f"{USPTO_NAMESPACE}.{USPTO_TRADEMARKS_TABLE}", table)
        except Exception:  # pragma: no cover
            logger.debug("USPTO trademarks Iceberg write failed", exc_info=True)

    def _register_lineage(self, df: pd.DataFrame) -> dict[str, Any]:
        try:
            return register_dataset_version(
                name="uspto.trademarks",
                provider="uspto",
                domain=str(self.domain),
                df=df,
                storage_uri=f"iceberg://{USPTO_NAMESPACE}.{USPTO_TRADEMARKS_TABLE}",
                file_count=1,
                meta={"rows": int(len(df))},
            )
        except Exception:  # pragma: no cover
            return {}


__all__ = ["USPTO_NAMESPACE", "USPTO_TRADEMARKS_TABLE", "UsptoTrademarksAdapter"]
