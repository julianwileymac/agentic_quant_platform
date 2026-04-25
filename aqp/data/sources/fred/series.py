"""FRED series adapter implementing the :class:`DataSourceAdapter` contract."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from aqp.config import settings
from aqp.data.catalog import register_data_links, register_dataset_version
from aqp.data.sources.base import (
    DataSourceAdapter,
    IdentifierSpec,
    ObservationsResult,
    ProbeResult,
)
from aqp.data.sources.domains import DataDomain
from aqp.data.sources.fred.catalog import upsert_fred_series
from aqp.data.sources.fred.client import FredClient, FredClientError
from aqp.data.sources.resolvers.identifiers import IdentifierResolver

logger = logging.getLogger(__name__)


_OBS_COLUMNS = ["observation_date", "value", "realtime_start", "realtime_end"]


class FredSeriesAdapter(DataSourceAdapter):
    """Adapter for FRED economic series."""

    source_key = "fred"
    display_name = "FRED Economic Series"
    domain = DataDomain.ECONOMIC_SERIES

    def __init__(
        self,
        client: FredClient | None = None,
        *,
        parquet_root: Path | str | None = None,
    ) -> None:
        self.client = client or FredClient()
        root = parquet_root or (settings.parquet_dir / "fred")
        self.parquet_root = Path(root)

    # ------------------------------------------------------------------
    # DataSourceAdapter API
    # ------------------------------------------------------------------

    def probe(self) -> ProbeResult:
        ok, message = self.client.probe()
        return ProbeResult.success(message) if ok else ProbeResult.failure(message)

    def fetch_metadata(
        self,
        *,
        query: str | None = None,
        series_id: str | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Return metadata for one series or for a search query."""
        if series_id:
            record = self.client.get_series(series_id)
            if record is None:
                return {"series_id": series_id, "found": False}
            return {"series_id": series_id, "found": True, "record": record}
        if not query:
            raise FredClientError("fetch_metadata requires either series_id or query")
        hits = self.client.search_series(query, limit=limit)
        return {"query": query, "count": len(hits), "results": hits}

    def fetch_observations(
        self,
        *,
        series_id: str,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        units: str | None = None,
        frequency: str | None = None,
        persist: bool = True,
        emit_lineage: bool = True,
    ) -> ObservationsResult:
        """Fetch observations for ``series_id`` and optionally persist."""
        observation_start = _coerce_date(start)
        observation_end = _coerce_date(end)
        raw_meta = self.client.get_series(series_id) or {"id": series_id}
        raw_obs = self.client.get_observations(
            series_id,
            observation_start=observation_start,
            observation_end=observation_end,
            units=units,
            frequency=frequency,
        )

        if not raw_obs:
            return ObservationsResult(data=pd.DataFrame(columns=_OBS_COLUMNS))

        df = pd.DataFrame(raw_obs)
        # Normalise types: dates, numeric values, drop missing observations (".").
        df = df.rename(columns={"date": "observation_date"})
        df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"].replace(".", pd.NA), errors="coerce")
        for col in ("realtime_start", "realtime_end"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
            else:
                df[col] = pd.NaT
        df = df.dropna(subset=["observation_date", "value"]).reset_index(drop=True)
        df = df[_OBS_COLUMNS]
        df["series_id"] = series_id

        storage_uri: str | None = None
        lineage: dict[str, Any] = {}
        data_links: list[dict[str, Any]] = []
        if persist and not df.empty:
            path = self._write_parquet(series_id, df)
            storage_uri = str(path)

            if emit_lineage:
                lineage = self._register_lineage(
                    series_id=series_id,
                    df=df,
                    storage_uri=storage_uri,
                    frequency=raw_meta.get("frequency_short"),
                    metadata=raw_meta,
                )
                version_id = lineage.get("dataset_version_id")
                if version_id:
                    entry = {
                        "entity_kind": "fred_series",
                        "entity_id": series_id,
                        "coverage_start": df["observation_date"].min(),
                        "coverage_end": df["observation_date"].max(),
                        "row_count": int(len(df)),
                        "meta": {"units": raw_meta.get("units_short")},
                    }
                    register_data_links(
                        dataset_version_id=version_id,
                        source_name=self.source_key,
                        entity_rows=[entry],
                    )
                    data_links.append(entry)

            # Persist FRED series master row.
            upsert_fred_series(raw_meta)

            # Emit identifier link for the series_id.
            IdentifierResolver(source_name=self.source_key).upsert_links(
                [
                    IdentifierSpec(
                        scheme="fred_series_id",
                        value=series_id,
                        entity_kind="fred_series",
                        entity_id=series_id,
                        meta={"title": raw_meta.get("title")},
                    )
                ],
                default_entity_kind="fred_series",
            )

        return ObservationsResult(
            data=df,
            lineage=lineage,
            identifiers=[
                IdentifierSpec(
                    scheme="fred_series_id",
                    value=series_id,
                    entity_kind="fred_series",
                    entity_id=series_id,
                )
            ],
            data_links=data_links,
        )

    def capabilities(self) -> dict[str, Any]:
        return {
            "domain": str(self.domain),
            "source_key": self.source_key,
            "frequencies": ["Daily", "Weekly", "Monthly", "Quarterly", "Annual"],
            "supports_historical": True,
            "supports_realtime_vintages": True,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _write_parquet(self, series_id: str, df: pd.DataFrame) -> Path:
        self.parquet_root.mkdir(parents=True, exist_ok=True)
        safe = series_id.replace("/", "_").replace("\\", "_").upper()
        path = self.parquet_root / f"{safe}.parquet"
        if path.exists():
            try:
                existing = pd.read_parquet(path)
                combined = pd.concat([existing, df], ignore_index=True)
                combined = combined.drop_duplicates(
                    subset=["observation_date", "series_id"], keep="last"
                ).sort_values("observation_date")
                pq.write_table(pa.Table.from_pandas(combined), path)
                return path
            except Exception:
                logger.debug("fred: could not merge %s, overwriting", path, exc_info=True)
        pq.write_table(pa.Table.from_pandas(df.sort_values("observation_date")), path)
        return path

    def _register_lineage(
        self,
        *,
        series_id: str,
        df: pd.DataFrame,
        storage_uri: str | None,
        frequency: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        lineage_df = df.rename(columns={"observation_date": "timestamp"})
        lineage_df["vt_symbol"] = f"FRED:{series_id}"
        try:
            return register_dataset_version(
                name=f"fred.{series_id}",
                provider="fred",
                domain=str(self.domain),
                df=lineage_df,
                storage_uri=storage_uri,
                frequency=frequency,
                meta={
                    "series_id": series_id,
                    "units": metadata.get("units_short"),
                    "seasonal_adj": metadata.get("seasonal_adjustment_short"),
                    "title": metadata.get("title"),
                },
                file_count=1,
            )
        except Exception:  # pragma: no cover — catalog helper already best-effort
            logger.debug("fred lineage registration failed", exc_info=True)
            return {}


def _coerce_date(value: str | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return str(value)
