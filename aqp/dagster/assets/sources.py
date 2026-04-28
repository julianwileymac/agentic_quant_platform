"""One Dagster asset per AQP source fetcher.

Each asset constructs a tiny :class:`PipelineManifest` (source ->
iceberg sink) and runs it through the engine. The asset name maps to
the Iceberg table the data lands in, so the cluster's Dagster can
schedule them deterministically.
"""
from __future__ import annotations

from typing import Any

from dagster import AssetExecutionContext, AssetKey, asset

from aqp.dagster.resources import AqpEngineResource


def _run(
    context: AssetExecutionContext,
    *,
    namespace: str,
    table: str,
    source_name: str,
    source_kwargs: dict[str, Any],
    domain: str,
    transforms: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    engine: AqpEngineResource = context.resources.engine
    manifest = {
        "name": f"{table}_asset",
        "namespace": namespace,
        "description": f"Dagster asset wrapping {source_name}",
        "source": {"name": source_name, "kwargs": source_kwargs},
        "transforms": transforms or [],
        "sink": {
            "name": "sink.iceberg",
            "kwargs": {
                "namespace": namespace,
                "table": table,
                "provider": source_name.split(".", 1)[-1],
                "domain": domain,
                "dagster_asset_key": "/".join(AssetKey([namespace, table]).path),
            },
        },
        "compute": {"backend": "auto"},
        "tags": ["dagster", source_name.split(".", 1)[-1]],
    }
    result = engine.run_manifest(manifest)
    context.log.info("rows_written=%d", result.get("total_rows_written") or 0)
    context.add_output_metadata(
        {
            "rows_written": int(
                sum(t.get("rows_written", 0) for t in result.get("tables", []))
            ),
            "tables": [t.get("iceberg_identifier") for t in result.get("tables", [])],
            "lineage": str(result.get("lineage") or {})[:512],
        }
    )
    return result


# ---------------------------------------------------------------------------
# Regulatory + reference assets
# ---------------------------------------------------------------------------


@asset(
    description="Ingest CFPB consumer complaints via the source.cfpb fetcher.",
    group_name="aqp_sources",
    required_resource_keys={"engine"},
)
def cfpb_complaints(context: AssetExecutionContext) -> dict[str, Any]:
    return _run(
        context,
        namespace="aqp_cfpb",
        table="complaints",
        source_name="source.cfpb",
        source_kwargs={"max_pages": 5},
        domain="regulatory.cfpb.complaint",
    )


@asset(
    description="Ingest FDA recalls via source.fda(endpoint=recalls).",
    group_name="aqp_sources",
    required_resource_keys={"engine"},
)
def fda_recalls(context: AssetExecutionContext) -> dict[str, Any]:
    return _run(
        context,
        namespace="aqp_fda",
        table="recalls",
        source_name="source.fda",
        source_kwargs={"endpoint": "recalls", "max_pages": 5},
        domain="regulatory.fda.recall",
    )


@asset(
    description="Ingest USPTO patents via source.uspto(endpoint=patents).",
    group_name="aqp_sources",
    required_resource_keys={"engine"},
)
def uspto_patents(context: AssetExecutionContext) -> dict[str, Any]:
    return _run(
        context,
        namespace="aqp_uspto",
        table="patents",
        source_name="source.uspto",
        source_kwargs={"endpoint": "patents", "max_pages": 5},
        domain="regulatory.uspto.patent",
    )


@asset(
    description="Ingest GDELT GKG window via source.gdelt.",
    group_name="aqp_sources",
    required_resource_keys={"engine"},
)
def gdelt_events(context: AssetExecutionContext) -> dict[str, Any]:
    return _run(
        context,
        namespace="aqp_gdelt",
        table="events",
        source_name="source.gdelt",
        source_kwargs={"subject_filter_only": True},
        domain="events.gdelt",
    )


@asset(
    description="FRED canonical macro series (1Y horizon).",
    group_name="aqp_sources",
    required_resource_keys={"engine"},
)
def fred_observations(context: AssetExecutionContext) -> dict[str, Any]:
    return _run(
        context,
        namespace="aqp_fred",
        table="observations",
        source_name="source.fred",
        source_kwargs={"series_id": "DGS10"},
        domain="economic.series",
    )


@asset(
    description="SEC EDGAR filings index for the largest issuers.",
    group_name="aqp_sources",
    required_resource_keys={"engine"},
)
def sec_filings(context: AssetExecutionContext) -> dict[str, Any]:
    return _run(
        context,
        namespace="aqp_sec",
        table="filings_index",
        source_name="source.sec_filings",
        source_kwargs={"cik": "0000320193"},  # AAPL — illustrative
        domain="filings.index",
    )


# ---------------------------------------------------------------------------
# Symbol taxonomy
# ---------------------------------------------------------------------------


@asset(
    description="FinanceDatabase taxonomy — equities seed.",
    group_name="aqp_sources",
    required_resource_keys={"engine"},
)
def finance_database_equities(context: AssetExecutionContext) -> dict[str, Any]:
    return _run(
        context,
        namespace="aqp_finance_database",
        table="equities",
        source_name="source.finance_database",
        source_kwargs={"asset_class": "equities"},
        domain="taxonomy.equity",
    )


@asset(
    description="FinanceDatabase taxonomy — etfs seed.",
    group_name="aqp_sources",
    required_resource_keys={"engine"},
)
def finance_database_etfs(context: AssetExecutionContext) -> dict[str, Any]:
    return _run(
        context,
        namespace="aqp_finance_database",
        table="etfs",
        source_name="source.finance_database",
        source_kwargs={"asset_class": "etfs"},
        domain="taxonomy.etf",
    )


@asset(
    description="FinanceDatabase taxonomy — indices seed.",
    group_name="aqp_sources",
    required_resource_keys={"engine"},
)
def finance_database_indices(context: AssetExecutionContext) -> dict[str, Any]:
    return _run(
        context,
        namespace="aqp_finance_database",
        table="indices",
        source_name="source.finance_database",
        source_kwargs={"asset_class": "indices"},
        domain="taxonomy.index",
    )


__all__ = [
    "cfpb_complaints",
    "fda_recalls",
    "finance_database_equities",
    "finance_database_etfs",
    "finance_database_indices",
    "fred_observations",
    "gdelt_events",
    "sec_filings",
    "uspto_patents",
]
