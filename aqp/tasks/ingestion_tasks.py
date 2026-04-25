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
    """Ingest a user's local CSV / Parquet files into AQP's lake."""
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
