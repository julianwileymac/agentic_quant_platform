"""Dagster factory helpers for fetcher-driven assets and transformations."""
from __future__ import annotations

import inspect as _inspect
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

import pyarrow as pa  # imported at module scope so Dagster's type-hint resolution finds it

from aqp.data.catalog.active_metadata import BusinessMetadata
from aqp.observability.fabric_bus import record_span

if TYPE_CHECKING:  # pragma: no cover - typing only
    from aqp.data.fabric.schema_registry import CanonicalSchemaBase
    from aqp.data.fetchers.base import Fetcher
    from aqp.persistence.models_instrument_catalog import CatalogFeedEdge

logger = logging.getLogger(__name__)


class DagsterAssetFactory:
    """Generate Dagster definitions from Fetcher instances."""

    def build_asset(self, fetcher: "Fetcher") -> Any:
        try:
            import dagster as dg
        except ImportError as exc:
            raise RuntimeError("dagster is not installed") from exc

        try:
            import pyarrow as pa
        except ImportError as exc:
            raise RuntimeError("pyarrow is required for Dagster asset generation") from exc

        provider_name = str(getattr(fetcher, "PROVIDER_NAME", fetcher.__class__.__name__))
        provider_slug = provider_name.lower().replace(" ", "_")
        schedule = _provider_schedule(provider_slug)
        freshness_policy = _freshness_from_schedule(schedule, dg)
        metadata = dict(getattr(fetcher, "LOADER_SCHEMA_METADATA", {}))
        if schedule:
            metadata["execution_schedule"] = schedule

        @dg.asset(
            name=f"{provider_slug}_asset",
            group_name=provider_name,
            metadata=metadata,
            freshness_policy=freshness_policy,
        )
        def _asset(context) -> list[dict[str, Any]]:
            from aqp.data.engine.nodes import NodeContext

            run_id = str(getattr(context, "run_id", "dagster"))
            rows: list[dict[str, Any]] = []
            for edge in _provider_edges(provider_slug):
                try:
                    with _edge_symbol_override(fetcher, edge.provider_specific_ticker):
                        node_ctx = NodeContext(
                            pipeline_id="dagster",
                            run_id=run_id,
                            node_name=f"{provider_slug}:{edge.provider_specific_ticker}",
                            node_index=0,
                        )
                        batches = list(fetcher.fetch(node_ctx))
                        if not batches:
                            rows.append(
                                {
                                    "edge_id": str(edge.id),
                                    "ticker": str(edge.provider_specific_ticker),
                                    "records_persisted": 0,
                                    "status": "empty",
                                }
                            )
                            continue

                        source_table = pa.Table.from_batches(batches)
                        normalized = fetcher.normalize_schema(source_table)
                        namespace = f"aqp_{getattr(fetcher, 'MEDALLION_LAYER', 'bronze')}_{provider_slug}"
                        table_name = fetcher.CANONICAL_SCHEMA_CLASS.__name__.replace(
                            "Schema",
                            "",
                        ).lower()
                        medallion_layer = str(getattr(fetcher, "MEDALLION_LAYER", "bronze"))
                        persisted = fetcher.persist_to_iceberg(
                            normalized,
                            namespace=namespace,
                            table_name=table_name,
                            medallion_layer=medallion_layer,
                            business_metadata=BusinessMetadata(
                                data_owner="dagster",
                                semantic_definition=(
                                    f"{provider_name} ingest for "
                                    f"{fetcher.CANONICAL_SCHEMA_CLASS.__name__}"
                                ),
                                domain=f"fabric.{provider_slug}",
                                extras={
                                    "edge_id": str(edge.id),
                                    "provider_specific_ticker": str(edge.provider_specific_ticker),
                                },
                            ),
                        )
                        content_hash = (
                            fetcher._compute_request_hash(
                                edge_ids=[str(edge.id)],
                                time_window=None,
                            )
                            if hasattr(fetcher, "_compute_request_hash")
                            else str(getattr(fetcher, "content_hash", ""))
                        )
                        materialization = {
                            "records_persisted": int(persisted),
                            "content_hash": content_hash,
                            "iceberg_snapshot_id": None,
                            "otel_trace_id": _current_trace_id(),
                        }
                        context.log_event(dg.AssetMaterialization(metadata=materialization))
                        rows.append(
                            {
                                "edge_id": str(edge.id),
                                "ticker": str(edge.provider_specific_ticker),
                                "status": "success",
                                **materialization,
                            }
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "dagster asset edge failure provider=%s edge=%s ticker=%s (%s)",
                        provider_slug,
                        getattr(edge, "id", None),
                        getattr(edge, "provider_specific_ticker", None),
                        exc,
                    )
                    rows.append(
                        {
                            "edge_id": str(getattr(edge, "id", "")),
                            "ticker": str(getattr(edge, "provider_specific_ticker", "")),
                            "status": "error",
                            "error": str(exc),
                        }
                    )
            return rows

        return _asset

    def build_transformation_op(
        self,
        fn: Callable[..., Any],
        *,
        input_schema: type["CanonicalSchemaBase"],
        output_schema: type["CanonicalSchemaBase"],
        op_name: str | None = None,
    ) -> Any:
        try:
            import dagster as dg
        except ImportError as exc:
            raise RuntimeError("dagster is not installed") from exc

        resolved_name = op_name or getattr(fn, "__name__", "transformation_op")
        parameter_count = len(_inspect.signature(fn).parameters)

        @dg.op(
            name=resolved_name,
            tags={
                "input_schema": input_schema.__name__,
                "output_schema": output_schema.__name__,
            },
            config_schema={
                "params": dg.Field(
                    dg.Permissive(),
                    is_required=False,
                    default_value={},
                    description=(
                        f"Free-form params dict passed to the underlying "
                        f"{resolved_name!r} transformation function."
                    ),
                ),
            },
        )
        def _op(context, table):  # noqa: ANN001 - dagster validates context class identity
            params = dict(getattr(context, "op_config", None) or {}).get("params", {}) or {}
            validated_input = input_schema.validate_table(table)
            with record_span(
                f"dagster.op.{resolved_name}",
                attributes={
                    "input_schema": input_schema.__name__,
                    "output_schema": output_schema.__name__,
                    "input_rows": int(validated_input.num_rows),
                },
            ):
                if parameter_count >= 2:
                    output = fn(validated_input, params)
                else:
                    output = fn(validated_input)
            if not isinstance(output, pa.Table):
                raise TypeError(
                    f"{resolved_name} must return pyarrow.Table, got {type(output).__name__}"
                )
            return output_schema.validate_table(output)

        return _op


def _provider_schedule(provider_slug: str) -> str | None:
    from aqp.persistence.db import get_session
    from aqp.persistence.models import DataSource

    with get_session() as session:
        row = session.query(DataSource).filter(DataSource.name == provider_slug).first()
        if row is None:
            return None
        return str(row.execution_schedule) if row.execution_schedule else None


def _provider_edges(provider_slug: str) -> list["CatalogFeedEdge"]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models import DataSource
    from aqp.persistence.models_instrument_catalog import CatalogFeedEdge

    with get_session() as session:
        data_source = session.query(DataSource).filter(DataSource.name == provider_slug).first()
        if data_source is None:
            return []
        edges = (
            session.query(CatalogFeedEdge)
            .filter(
                CatalogFeedEdge.data_source_id == data_source.id,
                CatalogFeedEdge.is_enabled.is_(True),
            )
            .all()
        )
        return list(edges)


def _edge_symbol_override(fetcher: Any, ticker: str):
    class _Override:
        def __enter__(self_inner) -> Any:
            self_inner._had_symbol = hasattr(fetcher, "symbol")
            self_inner._had_symbols = hasattr(fetcher, "symbols")
            self_inner._symbol = getattr(fetcher, "symbol", None)
            self_inner._symbols = list(getattr(fetcher, "symbols", [])) if self_inner._had_symbols else []
            if self_inner._had_symbol:
                fetcher.symbol = ticker
            if self_inner._had_symbols:
                fetcher.symbols = [ticker]
            return fetcher

        def __exit__(self_inner, _exc_type, _exc, _tb) -> None:
            if self_inner._had_symbol:
                fetcher.symbol = self_inner._symbol
            if self_inner._had_symbols:
                fetcher.symbols = self_inner._symbols

    return _Override()


def _freshness_from_schedule(schedule: str | None, dagster_module: Any) -> Any:
    if not schedule:
        return None
    try:
        from croniter import croniter
    except ImportError:
        return None
    try:
        base = datetime.utcnow()
        iterator = croniter(schedule, base)
        first = iterator.get_next(datetime)
        second = iterator.get_next(datetime)
        lag_minutes = max(1, int((second - first).total_seconds() / 60))
        return dagster_module.FreshnessPolicy(maximum_lag_minutes=lag_minutes)
    except Exception:  # noqa: BLE001
        return None


def _current_trace_id() -> str:
    try:
        from opentelemetry import trace
    except ImportError:
        return ""
    span = trace.get_current_span()
    span_context = span.get_span_context()
    if not span_context or not span_context.trace_id:
        return ""
    return format(span_context.trace_id, "032x")


__all__ = ["DagsterAssetFactory"]
