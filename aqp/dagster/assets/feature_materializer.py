"""Dagster Phase 5 TA materializer.

`aqp.tasks.ml_test_tasks` reads whichever ``iceberg_identifier`` the
caller passes to `/ml/test/batch`. This job writes into
``aqp_gold_features.<table_name>`` so existing ML test flows can point
directly at these tables without task-side code changes.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import dagster as dg
import pyarrow as pa

from aqp.data.catalog.active_metadata import BusinessMetadata
from aqp.data.fabric.schema_registry import FeatureSchema, OHLCVSchema
from aqp.data.iceberg_catalog import append_arrow
from aqp.dagster.ops.ta_ops import (
    compute_bollinger_bands,
    compute_macd,
    compute_moving_averages,
    compute_rsi,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from aqp.data.fetchers.api.yfinance import YFinanceFetcher

logger = logging.getLogger(__name__)

GOLD_NAMESPACE = "aqp_gold_features"
PIPELINE_VERSION = "v1"


def _make_business_metadata(feature_name: str) -> BusinessMetadata:
    return BusinessMetadata(
        data_owner="aqp-data-fabric",
        semantic_definition=(
            "Technical-analysis feature rows produced by the Dagster "
            f"Phase 5 TA pipeline ({feature_name})."
        ),
        reliability_score=0.95,
        sla_class="tier-3-eod",
        domain="features.technical_analysis",
        extras={
            "pipeline_version": PIPELINE_VERSION,
            "feature_name": feature_name,
            "tags": ["fabric", "ta", feature_name],
        },
    )


@dg.op(
    out=dg.Out(
        dagster_type=Any,
        description="OHLCV pa.Table for downstream TA ops.",
    ),
    config_schema={
        "symbols": dg.Field(dg.Array(str), is_required=True),
        "interval": dg.Field(dg.String, is_required=False, default_value="1d"),
        "start": dg.Field(dg.String, is_required=False),
        "end": dg.Field(dg.String, is_required=False),
    },
)
def fetch_yfinance_ohlcv(context) -> pa.Table:  # noqa: ANN001 - dagster validates context class identity
    """Fetch OHLCV rows through the Phase 2 YFinance fetcher."""
    from aqp.data.engine.nodes import NodeContext
    from aqp.data.fetchers.api.yfinance import YFinanceFetcher

    cfg = dict(context.op_config or {})
    fetcher: YFinanceFetcher = YFinanceFetcher(
        symbols=list(cfg["symbols"]),
        interval=str(cfg.get("interval", "1d")),
        start=cfg.get("start"),
        end=cfg.get("end"),
    )

    node_ctx = NodeContext(
        pipeline_id="materialize_features",
        run_id=str(context.run_id),
        node_name="fetch_yfinance_ohlcv",
        node_index=0,
    )
    batches = list(fetcher.fetch(node_ctx))
    if batches:
        table = pa.Table.from_batches(batches)
    else:
        table = pa.Table.from_pylist([], schema=OHLCVSchema.CANONICAL_SCHEMA)

    validated = OHLCVSchema.validate_table(table)
    context.log.info("Fetched OHLCV rows=%d", int(validated.num_rows))
    return validated


@dg.op
def persist_features(  # noqa: ANN001 - dagster validates context class identity
    context,
    sma_table: pa.Table,
    rsi_table: pa.Table,
    bbands_table: pa.Table,
    macd_table: pa.Table,
) -> dict[str, int]:
    """Persist TA features to Iceberg under the gold medallion namespace."""
    results: dict[str, int] = {}
    for table_name, table in (
        ("moving_averages", FeatureSchema.validate_table(sma_table)),
        ("rsi", FeatureSchema.validate_table(rsi_table)),
        ("bollinger_bands", FeatureSchema.validate_table(bbands_table)),
        ("macd", FeatureSchema.validate_table(macd_table)),
    ):
        append_result = append_arrow(
            table=table,
            identifier=f"{GOLD_NAMESPACE}.{table_name}",
            medallion_layer="gold",
            business_metadata=_make_business_metadata(table_name),
        )
        rows_written = (
            int(append_result) if isinstance(append_result, int) else int(table.num_rows)
        )
        results[table_name] = rows_written
        context.log_event(
            dg.AssetMaterialization(
                asset_key=dg.AssetKey([GOLD_NAMESPACE, table_name]),
                metadata={
                    "rows_written": dg.MetadataValue.int(rows_written),
                    "namespace": dg.MetadataValue.text(GOLD_NAMESPACE),
                    "pipeline_version": dg.MetadataValue.text(PIPELINE_VERSION),
                },
            )
        )
    return results


@dg.job(
    name="materialize_features",
    tags={"pipeline_version": PIPELINE_VERSION, "data_layer": "gold"},
    config={
        "ops": {
            "compute_moving_averages": {"config": {"params": {"pipeline_version": PIPELINE_VERSION}}},
            "compute_rsi": {"config": {"params": {"pipeline_version": PIPELINE_VERSION}}},
            "compute_bollinger_bands": {"config": {"params": {"pipeline_version": PIPELINE_VERSION}}},
            "compute_macd": {"config": {"params": {"pipeline_version": PIPELINE_VERSION}}},
        }
    },
)
def materialize_features() -> None:
    raw = fetch_yfinance_ohlcv()
    sma = compute_moving_averages(raw)
    rsi = compute_rsi(raw)
    bbands = compute_bollinger_bands(raw)
    macd = compute_macd(raw)
    persist_features(sma, rsi, bbands, macd)


__all__ = [
    "GOLD_NAMESPACE",
    "PIPELINE_VERSION",
    "fetch_yfinance_ohlcv",
    "materialize_features",
    "persist_features",
]
