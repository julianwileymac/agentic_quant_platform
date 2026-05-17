from __future__ import annotations

import importlib
import inspect
import logging
import re
import traceback
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from celery import shared_task

from aqp.config import settings
from aqp.data.catalog.active_metadata import BusinessMetadata
from aqp.data.catalog.lineage import record_lineage
from aqp.data.engine import get_node_class
from aqp.data.engine.nodes import NodeContext
from aqp.data.fabric.idempotency import (
    check_or_insert_pending,
    compute_request_hash,
    update_ledger_status,
)
from aqp.data.fetchers import LOADER_REGISTRY
from aqp.data.fetchers.fabric_mixin import FabricFetcherMixin
from aqp.observability.fabric_bus import get_observability_bus, record_span
from aqp.persistence.db import get_session
from aqp.persistence.models import DataSource
from aqp.persistence.models_instrument_catalog import CatalogFeedEdge
from aqp.persistence.models_pipelines import FetcherRun
from aqp.tasks._progress import emit, emit_done, emit_error

logger = logging.getLogger(__name__)


def _as_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        return {}
    try:
        return dict(value)
    except Exception:  # noqa: BLE001
        return {}


def _sanitize_table_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "feed"


def _parse_timestamp(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


def _parse_time_window(
    value: tuple[str, str] | None,
) -> tuple[datetime, datetime] | None:
    if value is None:
        return None
    start = _parse_timestamp(str(value[0]))
    end = _parse_timestamp(str(value[1]))
    if end < start:
        start, end = end, start
    return start, end


def _time_window_label(window: tuple[datetime, datetime] | None) -> str | None:
    if window is None:
        return None
    start, end = window
    return f"{start.isoformat().replace('+00:00', 'Z')},{end.isoformat().replace('+00:00', 'Z')}"


def _span_ids(span: Any) -> tuple[str | None, str | None]:
    try:
        context = span.get_span_context()
    except Exception:  # noqa: BLE001
        return None, None
    trace_id = getattr(context, "trace_id", 0) or 0
    span_id = getattr(context, "span_id", 0) or 0
    trace_hex = f"{int(trace_id):032x}" if int(trace_id) else None
    span_hex = f"{int(span_id):016x}" if int(span_id) else None
    return trace_hex, span_hex


def _coerce_business_metadata(
    data_source: DataSource,
    *,
    namespace: str,
    table_name: str,
    medallion_layer: str,
    business_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    incoming = dict(business_metadata or {})
    owner = str(
        incoming.pop("data_owner", incoming.pop("owner", "aqp-data-fabric"))
    ).strip() or "aqp-data-fabric"
    semantic_definition = str(
        incoming.pop(
            "semantic_definition",
            incoming.pop(
                "semantic",
                f"Auto-sync ingestion for feed {data_source.name}",
            ),
        )
    ).strip() or f"Auto-sync ingestion for feed {data_source.name}"
    domain = incoming.pop("domain", f"fabric.{data_source.name}")
    reliability_score = incoming.pop("reliability_score", None)
    sla_class = incoming.pop("sla_class", None)

    extras = _as_mapping(incoming.pop("extras", {}))
    if "tags" in incoming:
        extras["tags"] = list(incoming.pop("tags") or [])
    extras.setdefault("tags", ["fabric", "auto-sync"])
    extras.setdefault("owner", owner)
    extras.setdefault("namespace", namespace)
    extras.setdefault("table_name", table_name)
    extras.setdefault("medallion_layer", medallion_layer)
    if incoming:
        extras.update(incoming)

    payload: dict[str, Any] = {
        "data_owner": owner,
        "semantic_definition": semantic_definition,
        "domain": str(domain) if domain is not None else None,
        "extras": extras,
    }
    if reliability_score is not None:
        payload["reliability_score"] = float(reliability_score)
    if sla_class is not None:
        payload["sla_class"] = str(sla_class)
    return payload


def _connection_params_for(data_source: DataSource) -> dict[str, Any]:
    params: dict[str, Any] = {}
    params.update(_as_mapping(getattr(data_source, "connection_params", None)))
    params.update(_as_mapping(getattr(data_source, "rate_limit_params", None)))
    meta = _as_mapping(getattr(data_source, "meta", None))
    params.update(_as_mapping(meta.get("connection_params")))
    capabilities = _as_mapping(getattr(data_source, "capabilities", None))
    params.update(_as_mapping(capabilities.get("connection_params")))
    return params


def _candidate_loader_aliases(data_source: DataSource) -> list[str]:
    aliases: list[str] = []
    if data_source.name:
        aliases.append(str(data_source.name))
        aliases.append(f"source.{data_source.name}")
    if data_source.kind:
        aliases.append(str(data_source.kind))
        aliases.append(f"source.{data_source.kind}")
    # Preserve order while deduping.
    seen: set[str] = set()
    ordered: list[str] = []
    for alias in aliases:
        if alias in seen:
            continue
        seen.add(alias)
        ordered.append(alias)
    return ordered


def _resolve_loader_class(data_source: DataSource) -> type:
    """Resolve a fetcher class from loader_class_path or registered aliases."""
    loader_cls: Any | None = None

    if data_source.loader_class_path:
        module_path, _, class_name = str(data_source.loader_class_path).rpartition(".")
        if not module_path or not class_name:
            raise ImportError(
                f"Invalid loader_class_path={data_source.loader_class_path!r} "
                f"for feed {data_source.id}"
            )
        module = importlib.import_module(module_path)
        loader_cls = getattr(module, class_name, None)
        if loader_cls is None:
            raise ImportError(
                f"Loader class {class_name!r} not found in module {module_path!r}"
            )
    else:
        for alias in _candidate_loader_aliases(data_source):
            try:
                loader_cls = get_node_class(alias)
            except Exception:  # noqa: BLE001
                continue
            if loader_cls is not None:
                break

        if loader_cls is None:
            wanted = {str(data_source.name).lower(), str(data_source.kind).lower()}
            for candidate in LOADER_REGISTRY.values():
                provider_name = str(
                    getattr(
                        candidate,
                        "provider_name",
                        getattr(candidate, "PROVIDER_NAME", ""),
                    )
                ).lower()
                class_name = str(getattr(candidate, "__name__", "")).lower()
                if provider_name in wanted or class_name in wanted:
                    loader_cls = candidate
                    break

    if loader_cls is None:
        raise ImportError(
            f"Could not resolve loader class for feed_id={data_source.id} "
            f"(name={data_source.name!r}, kind={data_source.kind!r})"
        )

    if not isinstance(loader_cls, type):
        raise TypeError(f"Resolved loader for {data_source.id} is not a class: {loader_cls!r}")

    if not issubclass(loader_cls, FabricFetcherMixin):
        raise TypeError(
            f"Loader {loader_cls.__module__}.{loader_cls.__qualname__} does not inherit "
            "FabricFetcherMixin. Migrate it to the Phase 2 mixin first."
        )
    return loader_cls


def _build_loader_kwargs(
    data_source: DataSource,
    *,
    edges: list[CatalogFeedEdge],
    parsed_window: tuple[datetime, datetime] | None,
) -> dict[str, Any]:
    params = _connection_params_for(data_source)
    for edge in edges:
        params.update(_as_mapping(edge.edge_metadata_params))

    symbols = [str(edge.provider_specific_ticker) for edge in edges if edge.provider_specific_ticker]
    params.setdefault("symbols", symbols)
    if len(symbols) == 1:
        params.setdefault("symbol", symbols[0])
        params.setdefault("ticker", symbols[0])
        params.setdefault("series_id", symbols[0])

    if parsed_window is not None:
        start, end = parsed_window
        params.setdefault("start", start)
        params.setdefault("end", end)
        params.setdefault("start_date", start.strftime("%Y%m%d"))
        params.setdefault("end_date", end.strftime("%Y%m%d"))
        params.setdefault("time_window", (start, end))

    return params


def _instantiate_loader(loader_cls: type, kwargs: dict[str, Any]) -> Any:
    try:
        return loader_cls(**kwargs)
    except TypeError:
        signature = inspect.signature(loader_cls.__init__)
        accepts_var_kw = any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in signature.parameters.values()
        )
        if accepts_var_kw:
            raise
        allowed = {
            name
            for name, param in signature.parameters.items()
            if name != "self"
            and param.kind
            in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        }
        filtered = {key: value for key, value in kwargs.items() if key in allowed}
        if filtered == kwargs:
            raise
        return loader_cls(**filtered)


def _batch_to_rows(batch: Any) -> list[dict[str, Any]]:
    if batch is None:
        return []
    if hasattr(batch, "to_pylist") and callable(getattr(batch, "to_pylist")):
        return [dict(row) for row in batch.to_pylist()]
    if hasattr(batch, "to_pandas") and callable(getattr(batch, "to_pandas")):
        frame = batch.to_pandas()
        return [dict(row) for row in frame.to_dict(orient="records")]
    if isinstance(batch, list):
        return [dict(row) for row in batch if isinstance(row, dict)]
    if isinstance(batch, tuple):
        return [dict(row) for row in batch if isinstance(row, dict)]
    return []


def _create_fetcher_run(
    *,
    source_name: str,
    fetcher_alias: str,
    task_id: str,
    data_source_id: str,
) -> str | None:
    try:
        with get_session() as session:
            row = FetcherRun(
                source_name=source_name,
                fetcher_alias=fetcher_alias,
                status="running",
                started_at=datetime.utcnow(),
                extras={"task_id": task_id, "data_source_id": data_source_id},
            )
            session.add(row)
            session.flush()
            return str(row.id)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to create FetcherRun for data_source_id=%s", data_source_id)
        return None


def _update_fetcher_run(
    fetcher_run_id: str | None,
    *,
    status: str,
    rows_produced: int | None = None,
    error: str | None = None,
) -> None:
    if not fetcher_run_id:
        return
    try:
        with get_session() as session:
            row = session.query(FetcherRun).filter(FetcherRun.id == fetcher_run_id).first()
            if row is None:
                return
            row.status = status
            row.finished_at = datetime.utcnow()
            if rows_produced is not None:
                row.rows_produced = max(0, int(rows_produced))
            if error is not None:
                row.error = error
            session.add(row)
            session.flush()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to update FetcherRun id=%s", fetcher_run_id)


@shared_task(
    name="aqp.tasks.sync_feed",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_feed(
    self,
    *,
    feed_id: str,
    time_window: tuple[str, str] | None = None,
    namespace: str = "aqp_bronze_feeds",
    table_name: str | None = None,
    medallion_layer: str = "bronze",
    business_metadata: dict[str, Any] | None = None,
    edge_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Run one feed sync and persist into Iceberg via FabricFetcherMixin."""
    task_id = self.request.id or f"local-{uuid.uuid4().hex[:8]}"
    emit(task_id, "start", f"Starting feed sync for {feed_id}")

    ledger_id: str | None = None
    fetcher_run_id: str | None = None
    total_extracted = 0
    total_persisted = 0

    try:
        parsed_window = _parse_time_window(time_window)
        with get_session() as session:
            data_source_row = (
                session.query(DataSource)
                .filter(DataSource.id == str(feed_id))
                .first()
            )
            if data_source_row is None:
                raise ValueError(f"DataSource {feed_id!r} not found")

            edges_query = session.query(CatalogFeedEdge).filter(
                CatalogFeedEdge.data_source_id == str(feed_id),
                CatalogFeedEdge.is_enabled.is_(True),
            )
            if edge_ids is not None:
                edge_filter = [str(edge_id) for edge_id in edge_ids]
                edges_query = edges_query.filter(CatalogFeedEdge.id.in_(edge_filter))
            edge_rows = list(edges_query.order_by(CatalogFeedEdge.id).all())

            data_source = SimpleNamespace(
                id=str(data_source_row.id),
                name=str(data_source_row.name or ""),
                kind=str(data_source_row.kind or ""),
                loader_class_path=data_source_row.loader_class_path,
                connection_params=_as_mapping(
                    getattr(data_source_row, "connection_params", None)
                ),
                rate_limit_params=_as_mapping(
                    getattr(data_source_row, "rate_limit_params", None)
                ),
                meta=_as_mapping(getattr(data_source_row, "meta", None)),
                capabilities=_as_mapping(
                    getattr(data_source_row, "capabilities", None)
                ),
            )
            edges = [
                SimpleNamespace(
                    id=str(edge.id),
                    provider_specific_ticker=str(edge.provider_specific_ticker or ""),
                    edge_metadata_params=_as_mapping(edge.edge_metadata_params),
                )
                for edge in edge_rows
            ]

        resolved_table_name = _sanitize_table_name(
            table_name or str(data_source.name or "feed")
        )
        edge_id_list = [str(edge.id) for edge in edges]
        request_hash = compute_request_hash(
            data_source_id=str(data_source.id),
            edge_ids=edge_id_list,
            time_window=parsed_window,
            extras={
                "namespace": namespace,
                "table_name": resolved_table_name,
                "medallion_layer": medallion_layer,
            },
        )
        metadata_payload = _coerce_business_metadata(
            data_source,
            namespace=namespace,
            table_name=resolved_table_name,
            medallion_layer=medallion_layer,
            business_metadata=business_metadata,
        )
        business_meta = BusinessMetadata(**metadata_payload)

        with record_span(
            "task.sync_feed",
            attributes={
                "feed_id": str(feed_id),
                "data_source_name": str(data_source.name),
                "namespace": namespace,
                "table_name": resolved_table_name,
                "medallion_layer": medallion_layer,
                "edge_count": len(edge_id_list),
            },
        ) as task_span:
            otel_trace_id, otel_span_id = _span_ids(task_span)
            ledger_id, is_skip = check_or_insert_pending(
                data_source_id=str(data_source.id),
                request_hash=request_hash,
                requested_time_window=_time_window_label(parsed_window),
                business_metadata={
                    **business_meta.to_json(),
                    "namespace": namespace,
                    "table_name": resolved_table_name,
                    "medallion_layer": medallion_layer,
                },
                otel_trace_id=otel_trace_id,
                otel_span_id=otel_span_id,
            )
            if is_skip:
                result = {
                    "ledger_id": ledger_id,
                    "records_extracted": 0,
                    "records_persisted": 0,
                    "skipped": True,
                }
                emit_done(task_id, result=result)
                return result

            if not edges:
                raise ValueError(f"No enabled CatalogFeedEdge rows found for feed {feed_id}")

            update_ledger_status(
                str(ledger_id),
                status="RUNNING",
                records_extracted=0,
                records_persisted=0,
            )

            loader_cls = _resolve_loader_class(data_source)
            fetcher_run_id = _create_fetcher_run(
                source_name=str(data_source.name),
                fetcher_alias=f"{loader_cls.__module__}.{loader_cls.__qualname__}",
                task_id=str(task_id),
                data_source_id=str(data_source.id),
            )
            if ledger_id and fetcher_run_id:
                update_ledger_status(
                    str(ledger_id),
                    status="RUNNING",
                    fetcher_run_id=fetcher_run_id,
                )

            loader_kwargs = _build_loader_kwargs(
                data_source,
                edges=edges,
                parsed_window=parsed_window,
            )
            loader = _instantiate_loader(loader_cls, loader_kwargs)
            flush_threshold = max(
                1,
                int(getattr(settings, "fabric_sync_flush_rows", 10_000) or 10_000),
            )
            bus = get_observability_bus()
            buffer: list[dict[str, Any]] = []

            def _flush_buffer() -> None:
                nonlocal buffer, total_persisted
                if not buffer:
                    return
                table = loader.normalize_schema(buffer)
                persisted = int(
                    loader.persist_to_iceberg(
                        table,
                        namespace=namespace,
                        table_name=resolved_table_name,
                        medallion_layer=medallion_layer,
                        business_metadata=business_meta,
                    )
                )
                total_persisted += max(0, persisted)
                update_ledger_status(
                    str(ledger_id),
                    status="RUNNING",
                    records_extracted=total_extracted,
                    records_persisted=total_persisted,
                    fetcher_run_id=fetcher_run_id,
                )
                emit(
                    task_id,
                    "fetched-batch",
                    f"Persisted {persisted} rows",
                    records_extracted=total_extracted,
                    records_persisted=total_persisted,
                    batch_size=len(buffer),
                )
                buffer = []

            with record_span(
                "task.sync_feed.fetch",
                attributes={
                    "feed_id": str(feed_id),
                    "provider": str(getattr(loader, "PROVIDER_NAME", loader_cls.__name__)),
                    "flush_threshold": flush_threshold,
                },
            ):
                for batch in loader.fetch(
                    NodeContext(
                        pipeline_id=f"feed:{feed_id}",
                        run_id=str(task_id),
                        node_name=str(data_source.name),
                        node_index=0,
                    )
                ):
                    rows = _batch_to_rows(batch)
                    if not rows:
                        continue
                    total_extracted += len(rows)
                    bus.records_fetched.add(
                        len(rows),
                        attributes={
                            "feed_id": str(feed_id),
                            "data_source": str(data_source.name),
                        },
                    )
                    buffer.extend(rows)
                    if len(buffer) >= flush_threshold:
                        _flush_buffer()
                _flush_buffer()

        lineage_details = {
            "data_source_id": str(data_source.id),
            "feed_id": str(feed_id),
            "edges": edge_id_list,
            "request_hash": request_hash,
        }
        target_identifier = f"{namespace}.{resolved_table_name}"
        update_ledger_status(
            str(ledger_id),
            status="SUCCESS",
            records_extracted=total_extracted,
            records_persisted=total_persisted,
            lineage_snapshot={
                "target": target_identifier,
                "details": lineage_details,
            },
            fetcher_run_id=fetcher_run_id,
        )
        _update_fetcher_run(
            fetcher_run_id,
            status="ok",
            rows_produced=total_persisted,
        )
        record_lineage(
            transform_kind="ingest.fabric.sync_feed",
            target=target_identifier,
            actor="celery",
            actor_kind="service",
            service_name=str(getattr(loader, "PROVIDER_NAME", data_source.name)),
            rows_written=total_persisted,
            medallion_layer=medallion_layer,
            run_id=str(task_id),
            details=lineage_details,
            summary=f"Synced {total_persisted} rows for feed {feed_id}",
        )

        result = {
            "ledger_id": str(ledger_id),
            "records_extracted": total_extracted,
            "records_persisted": total_persisted,
            "skipped": False,
        }
        emit_done(task_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        if ledger_id:
            update_ledger_status(
                str(ledger_id),
                status="FATAL_ERROR",
                records_extracted=total_extracted,
                records_persisted=total_persisted,
                error_traceback=tb,
                fetcher_run_id=fetcher_run_id,
            )
        _update_fetcher_run(
            fetcher_run_id,
            status="error",
            rows_produced=total_persisted,
            error=str(exc),
        )
        logger.error("sync_feed failed for feed_id=%s\n%s", feed_id, tb)
        emit_error(task_id, str(exc))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=self.default_retry_delay)
        raise


__all__ = [
    "sync_feed",
]
