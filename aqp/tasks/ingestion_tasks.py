"""Celery tasks for data ingestion + metadata indexing."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Any

from aqp.config import settings
from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


class _ActiveDailyAllBatchesFailed(RuntimeError):
    """Raised when every batch of ``ingest_active_daily_ohlcv`` fails (after ``emit_error``)."""


_ACTIVE_DAILY_LOCK_PREFIX = "aqp:lock:ingest_active_daily_ohlcv"
_ACTIVE_DAILY_LOCK_TTL_SECONDS = 6 * 3600


def _active_daily_lock_key(source: str | None) -> str:
    label = (source or "auto").strip().lower().replace(" ", "_")[:120]
    return f"{_ACTIVE_DAILY_LOCK_PREFIX}:{label}"


def _try_acquire_active_daily_lock(key: str, token: str, ttl_seconds: int) -> bool:
    try:
        import redis

        client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
        return bool(client.set(key, token, nx=True, ex=int(ttl_seconds)))
    except Exception as exc:
        logger.warning(
            "ingest_active_daily_ohlcv: Redis lock unavailable (%s); proceeding without lock",
            exc,
        )
        return True


def _release_active_daily_lock(key: str, token: str) -> None:
    try:
        import redis

        client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
        if client.get(key) == token:
            client.delete(key)
    except Exception:
        logger.debug("ingest_active_daily_ohlcv: lock release skipped", exc_info=True)


def _register_active_daily_catalog_summary(
    *,
    total_rows: int,
    loaded_symbol_count: int,
    provider: str,
    start: str,
    end: str,
    source_label: str,
    task_id: str,
) -> None:
    if total_rows <= 0:
        return
    try:
        from aqp.data.catalog import register_dataset_version

        bars_root = (settings.parquet_dir / "bars").resolve()
        register_dataset_version(
            name="bars.default",
            provider=provider,
            domain="market.bars",
            df=None,
            summary_row_count=int(total_rows),
            summary_symbol_count=int(loaded_symbol_count),
            frequency="1d",
            storage_uri=str(bars_root),
            meta={
                "task_id": task_id,
                "aggregated_run": True,
                "start": start,
                "end": end,
                "source": source_label,
                "physical_layout": "parquet_one_file_per_vt_symbol",
                "bars_root": str(bars_root),
            },
        )
    except Exception:
        logger.warning("ingest_active_daily_ohlcv: catalog summary registration failed", exc_info=True)


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year - years)


def _parse_end_date(value: str | None) -> date:
    if not value:
        return datetime.utcnow().date()
    return datetime.fromisoformat(str(value)[:10]).date()


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _active_instrument_vt_symbols() -> list[str]:
    from sqlalchemy import select

    from aqp.core.types import Symbol
    from aqp.persistence.db import get_session
    from aqp.persistence.models import Instrument

    with get_session() as session:
        rows = session.execute(
            select(Instrument.vt_symbol)
            .where(Instrument.is_active.is_(True))
            .order_by(Instrument.ticker.asc())
        ).scalars().all()

    symbols: list[str] = []
    seen: set[str] = set()
    for raw in rows:
        text = str(raw or "").strip().upper()
        if not text:
            continue
        vt_symbol = Symbol.parse(text).vt_symbol
        if vt_symbol not in seen:
            seen.add(vt_symbol)
            symbols.append(vt_symbol)
    return symbols


def _intraday_plan_summary(plan: Any) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "generated_at": plan.generated_at,
        "interval": plan.interval,
        "lookback_months": int(plan.lookback_months),
        "manifest_path": plan.manifest_path,
        "component_count": len(plan.components),
        "symbol_count": len({component.vt_symbol for component in plan.components}),
        "months": sorted({component.month for component in plan.components}),
        "status_counts": _component_status_counts(plan.components),
    }


def _component_status_counts(components: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for component in components:
        status = str(getattr(component, "status", "unknown") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _progress_callback(task_id: str):
    def _progress(stage: str, message: str, extras: dict[str, Any] | None = None) -> None:
        emit(task_id, stage, message, **(extras or {}))

    return _progress


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


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.ingest_active_daily_ohlcv")
def ingest_active_daily_ohlcv(
    self,
    years: int = 5,
    end: str | None = None,
    source: str | None = None,
    chunk_size: int = 100,
) -> dict[str, Any]:
    """Load daily OHLCV for every active instrument in the security master.

    **Storage:** rows are merged into the canonical Parquet lake at
    ``{AQP_PARQUET_DIR}/bars/<TICKER>_<EXCHANGE>.parquet`` (one file per
    ``vt_symbol``), not a new on-disk table per run. The metadata catalog
    records one new ``bars.default`` **version** per successful full run
    (see :func:`_register_active_daily_catalog_summary`).
    """
    task_id = self.request.id or "local"
    lock_key = _active_daily_lock_key(source)
    lock_token = task_id
    lock_held = False
    end_date = _parse_end_date(end)
    start_date = _subtract_years(end_date, int(years))
    symbols = _active_instrument_vt_symbols()
    source_label = str(source or "auto")

    if not symbols:
        message = "no active instruments found in the security master"
        emit_error(task_id, message)
        raise ValueError(message)

    batches = _chunks(symbols, max(1, int(chunk_size)))

    if not _try_acquire_active_daily_lock(lock_key, lock_token, _ACTIVE_DAILY_LOCK_TTL_SECONDS):
        message = "Another active daily OHLCV ingestion is already running; skipping duplicate"
        logger.warning("%s (task_id=%s lock_key=%s)", message, task_id, lock_key)
        emit(task_id, "skipped", message, lock_key=lock_key, concurrent=True)
        skipped: dict[str, Any] = {
            "skipped": True,
            "reason": "concurrent_run",
            "lock_key": lock_key,
            "requested_symbols": len(symbols),
        }
        emit_done(task_id, skipped)
        return skipped

    lock_held = True
    logger.info(
        "ingest_active_daily_ohlcv start task_id=%s symbols=%d batches=%d source=%s window=%s..%s",
        task_id,
        len(symbols),
        len(batches),
        source_label,
        start_date.isoformat(),
        end_date.isoformat(),
    )

    emit(
        task_id,
        "start",
        f"Loading {years} years of daily OHLCV for {len(symbols)} active instruments",
        symbols=len(symbols),
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        source=source_label,
        chunk_size=chunk_size,
    )

    total_rows = 0
    loaded_symbols: set[str] = set()
    errors: list[dict[str, Any]] = []
    resolved_source: Any = source
    try:
        from aqp.data.catalog import upsert_instruments_for_vt_symbols
        from aqp.data.ingestion import AlphaVantageSource, ingest

        if str(source or "").strip().lower() in {"alpha_vantage", "alphavantage"}:
            resolved_source = AlphaVantageSource(close_after_fetch=False)

        for index, batch in enumerate(batches, start=1):
            emit(
                task_id,
                "running",
                f"Loading batch {index}/{len(batches)} ({len(batch)} instruments)",
                batch=index,
                batches=len(batches),
                symbols=len(batch),
            )
            try:
                df = ingest(
                    symbols=batch,
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                    interval="1d",
                    source=resolved_source,
                    register_catalog_version=False,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "active daily OHLCV batch failed (batch=%s/%s size=%s task_id=%s)",
                    index,
                    len(batches),
                    len(batch),
                    task_id,
                )
                errors.append({"batch": index, "symbols": batch, "error": str(exc)})
                emit(
                    task_id,
                    "warning",
                    f"Batch {index}/{len(batches)} failed: {exc}",
                    batch=index,
                    error=str(exc),
                )
                continue

            total_rows += int(len(df))
            if not df.empty and "vt_symbol" in df.columns:
                loaded_symbols.update(str(v) for v in df["vt_symbol"].dropna().unique())
            if str(source or "").strip().lower() in {"alpha_vantage", "alphavantage"}:
                snapshot = getattr(getattr(resolved_source, "client", None), "rate_limiter", None)
                if snapshot is not None:
                    state = snapshot.snapshot()
                    emit(
                        task_id,
                        "rate_limit",
                        "Alpha Vantage rate limiter state",
                        requests_this_minute=state.requests_this_minute,
                        requests_today=state.requests_today,
                        next_refill_seconds=state.next_refill_seconds,
                    )

        result = {
            "n_rows": total_rows,
            "n_symbols": len(loaded_symbols),
            "requested_symbols": len(symbols),
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "interval": "1d",
            "source": source_label,
            "failed_batches": len(errors),
            "errors": errors[:10],
        }
        if total_rows == 0 and errors:
            message = f"all {len(errors)} active OHLCV batch(es) failed"
            logger.error("%s (task_id=%s)", message, task_id)
            emit_error(task_id, message, **result)
            raise _ActiveDailyAllBatchesFailed(message)

        upsert_instruments_for_vt_symbols(loaded_symbols)

        provider = getattr(resolved_source, "name", None) or source_label
        _register_active_daily_catalog_summary(
            total_rows=total_rows,
            loaded_symbol_count=len(loaded_symbols),
            provider=str(provider),
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            source_label=source_label,
            task_id=task_id,
        )

        if errors:
            logger.warning(
                "ingest_active_daily_ohlcv completed with partial failures task_id=%s failed_batches=%s",
                task_id,
                len(errors),
            )

        logger.info(
            "ingest_active_daily_ohlcv done task_id=%s rows=%s symbols=%s failed_batches=%s",
            task_id,
            total_rows,
            len(loaded_symbols),
            len(errors),
        )
        emit_done(task_id, result)
        return result

    except _ActiveDailyAllBatchesFailed:
        raise
    except Exception as exc:
        logger.exception("ingest_active_daily_ohlcv failed (task_id=%s)", task_id)
        emit_error(task_id, str(exc))
        raise
    finally:
        close = getattr(resolved_source, "close", None)
        if callable(close):
            close()
        if lock_held:
            _release_active_daily_lock(lock_key, lock_token)


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


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.ingest_alpha_vantage_history")
def ingest_alpha_vantage_history(
    self,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Fetch Alpha Vantage stock history and append it to Iceberg."""
    task_id = self.request.id or "local"
    symbols = list(payload.get("symbols") or [])
    emit(task_id, "start", f"Alpha Vantage history → Iceberg ({len(symbols)} symbols)")
    try:
        from aqp.data.sources.alpha_vantage.history import ingest_history

        history_payload = dict(payload)
        history_payload.pop("progress_cb", None)
        result = ingest_history(**history_payload, progress_cb=_progress_callback(task_id))
        response = result.to_dict()
        emit_done(task_id, response)
        return response
    except Exception as exc:
        logger.exception("ingest_alpha_vantage_history failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.load_alpha_vantage_endpoints")
def load_alpha_vantage_endpoints(
    self,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Multi-endpoint AlphaVantage bulk loader into the per-endpoint Iceberg lake."""
    task_id = self.request.id or "local"
    endpoints = list(payload.get("endpoints") or [])
    symbols = payload.get("symbols") or "all_active"
    filters = payload.get("filters") or {}
    limit = payload.get("limit")
    cache = bool(payload.get("cache", True))
    cache_ttl = payload.get("cache_ttl")

    emit(
        task_id,
        "start",
        f"AlphaVantage endpoint loader: {len(endpoints)} endpoint(s), symbols={symbols!r}",
        endpoints=endpoints,
        symbols=symbols if isinstance(symbols, str) else len(symbols),
    )

    def _progress(stage: str, message: str, extras: dict[str, Any] | None = None) -> None:
        emit(task_id, stage, message, **(extras or {}))

    try:
        from aqp.data.sources.alpha_vantage.bulk_loader import AlphaVantageBulkLoader

        loader = AlphaVantageBulkLoader(progress_cb=_progress)
        try:
            result = loader.run(
                endpoints=endpoints,
                symbols=symbols,
                filters=filters,
                limit=int(limit) if limit else None,
                cache=cache,
                cache_ttl=float(cache_ttl) if cache_ttl is not None else None,
            )
        finally:
            loader.close()
        response = result.to_dict()
        emit_done(task_id, response)
        return response
    except Exception as exc:
        logger.exception("load_alpha_vantage_endpoints failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.plan_alpha_vantage_intraday")
def plan_alpha_vantage_intraday(
    self,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build and persist 1-minute Alpha Vantage intraday request components."""

    task_id = self.request.id or "local"
    emit(task_id, "start", "Planning Alpha Vantage intraday request components")
    try:
        from aqp.data.sources.alpha_vantage.intraday_plan import build_intraday_plan

        plan = build_intraday_plan(**payload)
        response = _intraday_plan_summary(plan)
        emit_done(task_id, response)
        return response
    except Exception as exc:
        logger.exception("plan_alpha_vantage_intraday failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.load_alpha_vantage_intraday_components")
def load_alpha_vantage_intraday_components(
    self,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Load a batch of planned Alpha Vantage intraday components into Iceberg."""

    task_id = self.request.id or "local"
    emit(task_id, "start", "Loading Alpha Vantage intraday component batch")
    try:
        from aqp.data.sources.alpha_vantage.intraday_backfill import run_intraday_manifest

        load_payload = dict(payload)
        load_payload.pop("progress_cb", None)
        result = run_intraday_manifest(**load_payload, progress_cb=_progress_callback(task_id))
        response = result.to_dict()
        emit_done(task_id, response)
        return response
    except Exception as exc:
        logger.exception("load_alpha_vantage_intraday_components failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ingestion_tasks.run_alpha_vantage_intraday_delta")
def run_alpha_vantage_intraday_delta(
    self,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Plan and load one resumable Alpha Vantage intraday delta batch."""

    task_id = self.request.id or "local"
    emit(task_id, "start", "Running Alpha Vantage intraday delta cycle")
    try:
        from aqp.data.sources.alpha_vantage.intraday_backfill import run_intraday_manifest
        from aqp.data.sources.alpha_vantage.intraday_plan import build_intraday_plan

        plan_payload = dict(payload.get("plan") or payload)
        load_payload = dict(payload.get("load") or {})
        load_payload.pop("progress_cb", None)
        plan = build_intraday_plan(**plan_payload)
        emit(
            task_id,
            "planned",
            f"Planned {len(plan.components)} Alpha Vantage intraday components",
            manifest_path=plan.manifest_path,
            component_count=len(plan.components),
        )
        result = run_intraday_manifest(
            manifest_path=plan.manifest_path,
            progress_cb=_progress_callback(task_id),
            **load_payload,
        )
        response = {"plan": _intraday_plan_summary(plan), "load": result.to_dict()}
        emit_done(task_id, response)
        return response
    except Exception as exc:
        logger.exception("run_alpha_vantage_intraday_delta failed")
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
