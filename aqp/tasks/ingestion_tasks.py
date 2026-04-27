"""Celery tasks for data ingestion + metadata indexing."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.ingest_yahoo")
def ingest_yahoo(
    self,
    symbols: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    interval: str = "1d",
    source: str | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or "local"
    source_label = source or "auto"
    emit(task_id, "start", f"Downloading {len(symbols or [])} tickers (source={source_label})…")
    try:
        from aqp.data.ingestion import ingest

        df = ingest(symbols=symbols, start=start, end=end, interval=interval, source=source)
        lineage = dict(getattr(df, "attrs", {}).get("lineage") or {})
        result = {
            "n_rows": int(len(df)),
            "n_symbols": int(df["vt_symbol"].nunique()) if not df.empty else 0,
            **lineage,
        }
        emit_done(task_id, result)
        return result
    except Exception as e:  # pragma: no cover
        logger.exception("ingest_yahoo failed")
        emit_error(task_id, str(e))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.index_chroma")
def index_chroma(self) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", "Indexing parquet metadata into ChromaDB…")
    try:
        from aqp.data.chroma_store import ChromaStore

        n = ChromaStore().index_parquet_dir()
        emit_done(task_id, {"indexed": n})
        return {"indexed": n}
    except Exception as e:  # pragma: no cover
        logger.exception("index_chroma failed")
        emit_error(task_id, str(e))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.sync_alpha_vantage_universe")
def sync_alpha_vantage_universe(
    self,
    state: str = "active",
    limit: int | None = None,
    include_otc: bool = False,
    query: str | None = None,
) -> dict[str, Any]:
    """Refresh the managed instrument snapshot from Alpha Vantage listings."""
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Syncing Alpha Vantage universe (state={state})…")
    try:
        from aqp.data.sources.alpha_vantage.universe import AlphaVantageUniverseService

        service = AlphaVantageUniverseService()
        result = service.sync_snapshot(
            state=state,
            limit=limit,
            include_otc=include_otc,
            query=query,
        )
        emit_done(task_id, result)
        return result
    except Exception as exc:
        logger.exception("sync_alpha_vantage_universe failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.alpha_vantage_bulk_load")
def alpha_vantage_bulk_load(
    self,
    category: str,
    symbols: list[str] | None = None,
    date_range: dict[str, str] | None = None,
    extra_params: dict[str, Any] | None = None,
    target_bucket: str | None = None,
) -> dict[str, Any]:
    """Fetch Alpha Vantage data and persist raw payloads into AQP storage."""
    task_id = self.request.id or "local"
    symbols = list(symbols or [])
    emit(task_id, "start", f"Alpha Vantage bulk load: {category} ({len(symbols)} symbols)")
    try:
        from aqp.data.sources.alpha_vantage.bulk import run_bulk_load

        result = run_bulk_load(
            category=category,
            symbols=symbols,
            date_range=date_range or {},
            extra_params=extra_params or {},
            target_bucket=target_bucket,
        )
        payload = {
            "category": result.category,
            "uploaded_objects": result.uploaded_objects,
            "skipped_symbols": result.skipped_symbols,
            "errors": result.errors,
            "keys": result.keys,
            "duration_seconds": result.duration_seconds,
            "notes": result.notes,
            "lineage": result.lineage,
        }
        emit_done(task_id, payload)
        return payload
    except Exception as exc:
        logger.exception("alpha_vantage_bulk_load failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.load_local_directory")
def load_local_directory(
    self,
    source_dir: str,
    format: str = "csv",
    glob: str | None = None,
    column_map: dict[str, str] | None = None,
    tz: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Ingest a user's local CSV / Parquet files into AQP's lake.

    Backward-compatible OHLCV bars path. Generic non-bars datasets should
    use :func:`ingest_local_path` instead, which materializes into the
    Iceberg-managed catalog.
    """
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Loading {format} from {source_dir}…")
    try:
        from aqp.data.ingestion import LocalDirectoryLoader

        loader = LocalDirectoryLoader(
            source_dir=source_dir,
            format=format,
            glob=glob,
            column_map=column_map,
            tz=tz,
        )
        result = loader.run(overwrite=overwrite)
        emit_done(task_id, result)
        return result
    except Exception as e:  # pragma: no cover
        logger.exception("load_local_directory failed")
        emit_error(task_id, str(e))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.ingest_local_path")
def ingest_local_path(
    self,
    path: str,
    namespace: str | None = None,
    table_prefix: str | None = None,
    annotate: bool = True,
    max_rows_per_dataset: int | None = None,
    max_files_per_dataset: int | None = None,
    director_enabled: bool | None = None,
    allowed_namespaces: list[str] | None = None,
) -> dict[str, Any]:
    """Generic file / folder / ZIP ingestion into the Iceberg catalog.

    Uses :class:`aqp.data.pipelines.IngestionPipeline` for discovery,
    Director planning, streamed extraction, materialization, optional
    verifier-retry, and LLM annotation.
    """
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Ingesting {path} → iceberg ns={namespace or 'aqp'}")

    def _progress(phase: str, message: str) -> None:
        emit(task_id, phase, message)

    try:
        from aqp.data.pipelines import IngestionPipeline

        pipe = IngestionPipeline(
            progress_cb=_progress,
            max_rows_per_dataset=max_rows_per_dataset,
            max_files_per_dataset=max_files_per_dataset,
            director_enabled=director_enabled,
            allowed_namespaces=allowed_namespaces,
        )
        report = pipe.run_path(
            path=path,
            namespace=namespace,
            table_prefix=table_prefix,
            annotate=bool(annotate),
        )
        payload = report.to_dict()
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("ingest_local_path failed")
        emit_error(task_id, str(exc))
        raise


# ---------------------------------------------------------------------------
# Director-driven batch wrapper for the four regulatory corpora
# (CFPB / USPTO / FDA / SEC). Dispatches one ``ingest_local_path`` job
# per source path with the matching namespace and namespace allow-list.
# ---------------------------------------------------------------------------


_REGULATORY_DEFAULT_NAMESPACES = {
    "cfpb": "aqp_cfpb",
    "uspto": "aqp_uspto",
    "fda": "aqp_fda",
    "sec": "aqp_sec",
}


@celery_app.task(
    bind=True, name="aqp.tasks.ingestion_tasks.ingest_local_paths_with_director"
)
def ingest_local_paths_with_director(
    self,
    paths: list[str],
    namespace_per_path: dict[str, str] | None = None,
    *,
    annotate: bool = True,
    max_rows_per_dataset: int | None = None,
    max_files_per_dataset: int | None = None,
    director_enabled: bool | None = None,
) -> dict[str, Any]:
    """Director-aware batch wrapper.

    Runs the full discovery → director-plan → materialise → verify →
    annotate pipeline once per ``paths`` entry, in-process within a
    single Celery task. The Director is told about every namespace in
    ``namespace_per_path`` so it can route inter-source concerns
    correctly. Returns one :class:`IngestionReport` payload per path.
    """
    task_id = self.request.id or "local"
    paths = [str(p) for p in (paths or []) if str(p).strip()]
    namespace_per_path = dict(namespace_per_path or {})
    if not paths:
        emit_done(task_id, {"sources": []})
        return {"sources": []}

    allowed = sorted({namespace_per_path.get(p) or "aqp" for p in paths})
    emit(
        task_id,
        "start",
        f"Director batch: {len(paths)} sources, namespaces={allowed}",
    )

    def _progress(phase: str, message: str) -> None:
        emit(task_id, phase, message)

    sources: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        from aqp.data.pipelines import IngestionPipeline

        pipe = IngestionPipeline(
            progress_cb=_progress,
            max_rows_per_dataset=max_rows_per_dataset,
            max_files_per_dataset=max_files_per_dataset,
            director_enabled=director_enabled,
            allowed_namespaces=allowed,
        )
        for path in paths:
            ns = namespace_per_path.get(path) or "aqp"
            emit(task_id, "running", f"→ source={path} namespace={ns}")
            try:
                report = pipe.run_path(
                    path=path,
                    namespace=ns,
                    annotate=bool(annotate),
                )
                sources.append(report.to_dict())
            except Exception as exc:  # noqa: BLE001
                logger.exception("ingest of %s failed", path)
                errors.append(f"{path}: {exc}")
                sources.append(
                    {
                        "source_path": path,
                        "namespace": ns,
                        "errors": [str(exc)],
                    }
                )

        payload: dict[str, Any] = {
            "sources": sources,
            "errors": errors,
            "namespace_per_path": namespace_per_path,
            "allowed_namespaces": allowed,
        }
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("ingest_local_paths_with_director failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.annotate_dataset")
def annotate_dataset(
    self,
    iceberg_identifier: str,
    source_uri: str | None = None,
    truncated: bool = False,
    sample_rows: int = 25,
) -> dict[str, Any]:
    """Re-run the LLM annotation step for an existing Iceberg table."""
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Annotating {iceberg_identifier}")
    try:
        from aqp.data.pipelines.annotate import annotate_table

        result = annotate_table(
            iceberg_identifier=iceberg_identifier,
            source_uri=source_uri,
            truncated=bool(truncated),
            sample_rows=int(sample_rows),
        )
        payload = {"identifier": iceberg_identifier, **result.to_dict()}
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("annotate_dataset failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.ingest_fred_series")
def ingest_fred_series(
    self,
    series_ids: list[str] | str,
    start: str | None = None,
    end: str | None = None,
    units: str | None = None,
    frequency: str | None = None,
) -> dict[str, Any]:
    """Pull one or more FRED series into the parquet lake + lineage tables."""
    task_id = self.request.id or "local"
    if isinstance(series_ids, str):
        series_ids = [series_ids]
    series_ids = [s.strip().upper() for s in series_ids if s and s.strip()]
    emit(task_id, "start", f"Fetching {len(series_ids)} FRED series…")
    try:
        from aqp.data.sources.fred.series import FredSeriesAdapter

        adapter = FredSeriesAdapter()
        series_results: list[dict[str, Any]] = []
        total_rows = 0
        for series_id in series_ids:
            emit(task_id, "running", f"FRED → {series_id}")
            result = adapter.fetch_observations(
                series_id=series_id,
                start=start,
                end=end,
                units=units,
                frequency=frequency,
            )
            rows = result.row_count
            total_rows += rows
            series_results.append(
                {
                    "series_id": series_id,
                    "rows": rows,
                    "dataset_version_id": result.lineage.get("dataset_version_id"),
                    "dataset_hash": result.lineage.get("dataset_hash"),
                }
            )
        payload = {
            "source": "fred",
            "series": series_results,
            "total_rows": total_rows,
        }
        emit_done(task_id, payload)
        return payload
    except Exception as exc:
        logger.exception("ingest_fred_series failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.ingest_sec_filings")
def ingest_sec_filings(
    self,
    cik_or_ticker: str,
    form: str | list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    artifacts: list[str] | None = None,
    limit: int | None = 100,
) -> dict[str, Any]:
    """Populate the ``sec_filings`` index + optionally ingest parsed artifacts."""
    task_id = self.request.id or "local"
    artifacts = list(artifacts or [])
    emit(task_id, "start", f"SEC EDGAR → {cik_or_ticker} (forms={form})")
    try:
        from aqp.data.sources.sec.filings import SecFilingsAdapter

        adapter = SecFilingsAdapter()
        metadata = adapter.fetch_metadata(
            cik_or_ticker=cik_or_ticker,
            form=form,
            start=start,
            end=end,
            limit=limit,
        )
        result: dict[str, Any] = {
            "source": "sec_edgar",
            "cik_or_ticker": cik_or_ticker,
            "filings": int(metadata.get("count") or 0),
            "artifacts": {},
        }
        for artifact in artifacts:
            emit(task_id, "running", f"SEC → {cik_or_ticker} artifact={artifact}")
            obs = adapter.fetch_observations(
                cik_or_ticker=cik_or_ticker,
                artifact=artifact,
                form=form if isinstance(form, str) else None,
                start=start,
                end=end,
            )
            result["artifacts"][artifact] = {
                "rows": obs.row_count,
                "dataset_version_id": obs.lineage.get("dataset_version_id"),
            }
        emit_done(task_id, result)
        return result
    except Exception as exc:
        logger.exception("ingest_sec_filings failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.ingest_gdelt_window")
def ingest_gdelt_window(
    self,
    start: str,
    end: str,
    mode: str = "manifest",
    tickers: list[str] | None = None,
    themes: list[str] | None = None,
    subject_filter_only: bool | None = None,
    max_files: int | None = None,
) -> dict[str, Any]:
    """Download GDelt GKG slices for a time window and persist partitioned parquet."""
    task_id = self.request.id or "local"
    emit(task_id, "start", f"GDelt → {mode} window {start}..{end}")
    try:
        from aqp.data.sources.gdelt.adapter import GDeltAdapter

        adapter = GDeltAdapter()
        result = adapter.fetch_observations(
            start=start,
            end=end,
            mode=mode,  # type: ignore[arg-type]
            tickers=tickers,
            themes=themes,
            subject_filter_only=subject_filter_only,
            max_files=max_files,
        )
        payload = {
            "source": "gdelt",
            "mode": mode,
            "rows": result.row_count,
            "dataset_version_id": result.lineage.get("dataset_version_id"),
        }
        emit_done(task_id, payload)
        return payload
    except Exception as exc:
        logger.exception("ingest_gdelt_window failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.ingest_ibkr_historical")
def ingest_ibkr_historical(
    self,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch IBKR historical bars and persist them into the Parquet lake."""
    task_id = self.request.id or "local"
    req = dict(payload or {})
    vt_symbol = str(req.get("vt_symbol") or "").strip().upper()
    emit(task_id, "start", f"Requesting IBKR historical bars for {vt_symbol or 'symbol'}…")
    try:
        from aqp.data.ibkr_historical import IBKRHistoricalService
        from aqp.data.ingestion import write_parquet

        rows_hint = int(req.pop("rows", 0) or 0)
        overwrite = bool(req.pop("overwrite", False))

        service = IBKRHistoricalService()
        try:
            df = asyncio.run(service.fetch_bars(**req))
        except RuntimeError:
            # Defensive fallback in case a worker is already running an event loop.
            loop = asyncio.new_event_loop()
            try:
                df = loop.run_until_complete(service.fetch_bars(**req))
            finally:
                loop.close()

        if df.empty:
            result = {
                "source": "ibkr",
                "rows": 0,
                "symbols": [],
                "target": None,
                "hint_rows_limit": rows_hint or None,
            }
            emit_done(task_id, result)
            return result

        emit(task_id, "running", f"Fetched {len(df)} rows from IBKR, writing to Parquet lake…")
        target = write_parquet(df, overwrite=overwrite)
        result = {
            "source": "ibkr",
            "rows": int(len(df)),
            "symbols": sorted(df["vt_symbol"].unique().tolist()),
            "target": str(target),
            "hint_rows_limit": rows_hint or None,
            "overwrite": overwrite,
        }
        emit_done(task_id, result)
        return result
    except Exception as e:  # pragma: no cover
        logger.exception("ingest_ibkr_historical failed")
        emit_error(task_id, str(e))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.consolidate_iceberg_group")
def consolidate_iceberg_group(
    self,
    group_name: str,
    members: list[str],
    *,
    dry_run: bool = True,
    drop_members: bool = True,
) -> dict[str, Any]:
    """Physically merge Iceberg ``members`` into ``group_name``.

    Streams progress over ``/chat/stream/{task_id}`` so the UI can render
    a live consolidation log. Always returns a dict-shaped report
    regardless of dry-run vs. wet-run.
    """
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Consolidating {len(members)} members into {group_name}")
    try:
        from aqp.data.iceberg_consolidate import consolidate_group

        def _on_progress(percent: float, message: str) -> None:
            emit(task_id, "progress", message, percent=round(percent, 2))

        report = consolidate_group(
            group_name=group_name,
            members=members,
            dry_run=dry_run,
            drop_members=drop_members,
            on_progress=_on_progress,
        )
        result = report.to_dict()
        if report.error:
            emit_error(task_id, report.error, report=result)
        else:
            emit_done(task_id, result)
        return result
    except Exception as exc:  # pragma: no cover
        logger.exception("consolidate_iceberg_group failed")
        emit_error(task_id, str(exc))
        raise
