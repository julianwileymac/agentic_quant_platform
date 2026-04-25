"""Hybrid GDelt adapter.

Exposes a single :class:`GDeltAdapter` that can route ``fetch_window``
through either:

* ``manifest`` — download the raw 15-minute zips from the GDelt CDN,
  verify their MD5, optionally filter to registered instruments, and
  land the result as partitioned Parquet under
  ``{parquet_dir}/gdelt/year=.../month=.../day=...``.
* ``bigquery`` — issue a parametrised query against the public
  ``gdelt-bq.gdeltv2.gkg`` table.
* ``hybrid`` — run both paths; BigQuery is used for quick ad-hoc
  exploration and the Parquet partitions stay the system of record.

Which path fires is controlled per call via the ``mode`` argument,
so callers pick their poison at ingest time.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from aqp.config import settings
from aqp.data.catalog import register_data_links, register_dataset_version
from aqp.data.sources.base import (
    DataSourceAdapter,
    ObservationsResult,
    ProbeResult,
)
from aqp.data.sources.domains import DataDomain
from aqp.data.sources.gdelt.catalog import upsert_gdelt_mentions
from aqp.data.sources.gdelt.manifest import GDeltManifest
from aqp.data.sources.gdelt.parquet_sink import (
    GDeltDownloadError,
    decode_zip,
    derive_mentions,
    download_entry,
    subject_filter_rows,
    write_partitioned,
)
from aqp.data.sources.gdelt.subject_filter import SubjectFilter

logger = logging.getLogger(__name__)


Mode = Literal["manifest", "bigquery", "hybrid"]


class GDeltAdapter(DataSourceAdapter):
    """Hybrid GDelt GKG 2.0 adapter."""

    source_key = "gdelt"
    display_name = "GDELT GKG 2.0"
    domain = DataDomain.EVENTS_GDELT

    def __init__(
        self,
        *,
        manifest: GDeltManifest | None = None,
        parquet_root: Path | str | None = None,
    ) -> None:
        self.manifest = manifest or GDeltManifest()
        root = parquet_root or (
            Path(settings.parquet_dir) / settings.gdelt_parquet_subdir
        )
        self.parquet_root = Path(root)

    # ------------------------------------------------------------------
    # DataSourceAdapter API
    # ------------------------------------------------------------------

    def probe(self) -> ProbeResult:
        try:
            entries = self.manifest.entries()
        except Exception as exc:
            return ProbeResult.failure(f"manifest fetch failed: {exc}")
        return ProbeResult.success(
            f"manifest ok ({len(entries)} entries)",
            latest=str(entries[-1].timestamp) if entries else None,
        )

    def fetch_metadata(
        self,
        *,
        start: datetime | str,
        end: datetime | str,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Return the manifest slice covering ``[start, end]``."""
        entries = self.manifest.list_window(start, end, force_refresh=force_refresh)
        total_bytes = sum(e.size for e in entries)
        return {
            "start": str(start),
            "end": str(end),
            "count": len(entries),
            "total_bytes": total_bytes,
            "entries": [
                {
                    "url": e.url,
                    "size": e.size,
                    "md5": e.md5,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in entries
            ],
        }

    def fetch_observations(
        self,
        *,
        start: datetime | str,
        end: datetime | str,
        mode: Mode = "manifest",
        tickers: list[str] | None = None,
        themes: list[str] | None = None,
        subject_filter_only: bool | None = None,
        max_files: int | None = None,
        persist: bool = True,
        emit_lineage: bool = True,
    ) -> ObservationsResult:
        """Fetch GDelt data via manifest download or BigQuery federation."""
        subject_filter_only = (
            settings.gdelt_subject_filter_only
            if subject_filter_only is None
            else subject_filter_only
        )

        if mode == "bigquery":
            return self._fetch_bigquery(
                start=start,
                end=end,
                tickers=tickers,
                themes=themes,
                persist=persist,
                emit_lineage=emit_lineage,
            )
        if mode == "hybrid":
            manifest_result = self._fetch_manifest(
                start=start,
                end=end,
                tickers=tickers,
                subject_filter_only=subject_filter_only,
                max_files=max_files,
                persist=persist,
                emit_lineage=emit_lineage,
            )
            bq_result = self._fetch_bigquery(
                start=start,
                end=end,
                tickers=tickers,
                themes=themes,
                persist=False,
                emit_lineage=False,
            )
            combined = pd.concat(
                [manifest_result.data, bq_result.data], ignore_index=True
            )
            manifest_result.data = combined
            manifest_result.lineage.setdefault("bigquery", bq_result.lineage)
            return manifest_result
        return self._fetch_manifest(
            start=start,
            end=end,
            tickers=tickers,
            subject_filter_only=subject_filter_only,
            max_files=max_files,
            persist=persist,
            emit_lineage=emit_lineage,
        )

    def capabilities(self) -> dict[str, Any]:
        return {
            "domain": str(self.domain),
            "source_key": self.source_key,
            "modes": ["manifest", "bigquery", "hybrid"],
            "bigquery_table": settings.gdelt_bigquery_table,
            "frequencies": ["15m"],
        }

    # ------------------------------------------------------------------
    # Manifest path
    # ------------------------------------------------------------------

    def _fetch_manifest(
        self,
        *,
        start: datetime | str,
        end: datetime | str,
        tickers: list[str] | None,
        subject_filter_only: bool,
        max_files: int | None,
        persist: bool,
        emit_lineage: bool,
    ) -> ObservationsResult:
        entries = self.manifest.list_window(start, end)
        if max_files is not None:
            entries = entries[: int(max_files)]
        if not entries:
            return ObservationsResult(data=pd.DataFrame())

        subject_filter = SubjectFilter(tickers=tickers) if subject_filter_only else None
        frames: list[pd.DataFrame] = []
        mentions: list[dict[str, Any]] = []
        matched_entities: dict[str, dict[str, Any]] = {}
        file_count = 0

        for entry in entries:
            try:
                blob = download_entry(entry)
            except (GDeltDownloadError, Exception) as exc:
                logger.info("gdelt: skipping %s: %s", entry.filename, exc)
                continue
            try:
                df = decode_zip(blob)
            except Exception:
                logger.info("gdelt: could not decode %s", entry.filename, exc_info=True)
                continue
            if df.empty:
                continue
            report: list[dict[str, Any]] = []
            if subject_filter is not None:
                df, report = subject_filter_rows(df, subject_filter)
                if df.empty:
                    continue
            frames.append(df)
            file_count += 1
            if persist:
                write_partitioned(df, root=self.parquet_root)
            if report:
                derived = derive_mentions(df, report)
                mentions.extend(derived)
                for item in report:
                    key = str(item["instrument_id"])
                    agg = matched_entities.setdefault(
                        key,
                        {
                            "entity_kind": "instrument",
                            "entity_id": item["vt_symbol"],
                            "instrument_vt_symbol": item["vt_symbol"],
                            "row_count": 0,
                            "meta": {"ticker": item["ticker"]},
                        },
                    )
                    agg["row_count"] = int(agg["row_count"]) + 1

        if not frames:
            return ObservationsResult(data=pd.DataFrame())

        combined = pd.concat(frames, ignore_index=True)
        lineage: dict[str, Any] = {}
        if persist and emit_lineage:
            lineage = self._register_lineage(
                name="gdelt.gkg",
                df=combined,
                storage_uri=str(self.parquet_root),
                meta={
                    "mode": "manifest",
                    "file_count": file_count,
                    "subject_filter": subject_filter_only,
                },
            )
            version_id = lineage.get("dataset_version_id")
            if version_id and matched_entities:
                register_data_links(
                    dataset_version_id=version_id,
                    source_name=self.source_key,
                    entity_rows=list(matched_entities.values()),
                )
        if persist and mentions:
            upsert_gdelt_mentions(mentions)

        return ObservationsResult(data=combined, lineage=lineage)

    # ------------------------------------------------------------------
    # BigQuery path
    # ------------------------------------------------------------------

    def _fetch_bigquery(
        self,
        *,
        start: datetime | str,
        end: datetime | str,
        tickers: list[str] | None,
        themes: list[str] | None,
        persist: bool,
        emit_lineage: bool,
    ) -> ObservationsResult:
        from aqp.data.sources.gdelt.bigquery_client import (
            GDeltBigQueryClient,
            GDeltBigQueryError,
        )

        client = GDeltBigQueryClient()
        try:
            df = client.query_window(
                start=start,
                end=end,
                organizations=tickers,
                themes=themes,
            )
        except GDeltBigQueryError as exc:
            logger.warning("gdelt bigquery path disabled: %s", exc)
            return ObservationsResult(data=pd.DataFrame())

        lineage: dict[str, Any] = {}
        if persist and not df.empty and emit_lineage:
            lineage = self._register_lineage(
                name="gdelt.bigquery",
                df=df,
                storage_uri=None,
                meta={
                    "mode": "bigquery",
                    "table": settings.gdelt_bigquery_table,
                    "tickers": list(tickers or []),
                    "themes": list(themes or []),
                },
            )
        return ObservationsResult(data=df, lineage=lineage)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _register_lineage(
        self,
        *,
        name: str,
        df: pd.DataFrame,
        storage_uri: str | None,
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        lineage_df = df.copy()
        if "timestamp" not in lineage_df.columns:
            date_col = (
                "v21_date"
                if "v21_date" in lineage_df.columns
                else "DATE"
                if "DATE" in lineage_df.columns
                else None
            )
            if date_col:
                lineage_df["timestamp"] = pd.to_datetime(lineage_df[date_col], errors="coerce")
            else:
                lineage_df["timestamp"] = datetime.utcnow()
        if "vt_symbol" not in lineage_df.columns:
            lineage_df["vt_symbol"] = "GDELT:GKG"
        try:
            return register_dataset_version(
                name=name,
                provider="gdelt",
                domain=str(self.domain),
                df=lineage_df,
                storage_uri=storage_uri,
                frequency="15m",
                meta=meta,
                file_count=int(meta.get("file_count", 1) or 1),
            )
        except Exception:
            logger.debug("gdelt lineage registration failed", exc_info=True)
            return {}
