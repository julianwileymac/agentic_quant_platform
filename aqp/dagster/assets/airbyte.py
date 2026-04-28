"""Dagster assets for Airbyte control-plane visibility and materialization."""
from __future__ import annotations

from dagster import AssetExecutionContext, asset

from aqp.dagster.resources import AqpAirbyteResource, AqpEngineResource


@asset(
    description="Check Airbyte API health for the AQP data fabric.",
    group_name="airbyte",
    required_resource_keys={"airbyte"},
)
def airbyte_health(context: AssetExecutionContext) -> dict:
    airbyte: AqpAirbyteResource = context.resources.airbyte
    result = airbyte.health()
    context.add_output_metadata({"enabled": bool(result.get("ok"))})
    return result


@asset(
    description="Run a configured Airbyte staging materialization manifest through AQP.",
    group_name="airbyte",
    required_resource_keys={"engine"},
)
def airbyte_staging_materialization(context: AssetExecutionContext) -> dict:
    """Materialize an Airbyte staging manifest when supplied via run config."""
    engine: AqpEngineResource = context.resources.engine
    manifest = (context.op_config or {}).get("manifest")
    if not manifest:
        context.log.info("No Airbyte materialization manifest supplied; skipping.")
        return {"skipped": True, "reason": "missing_manifest"}
    result = engine.run_manifest(manifest)
    context.add_output_metadata(
        {
            "rows_written": int(result.get("total_rows_written") or 0),
            "tables": [row.get("iceberg_identifier") for row in result.get("tables", [])],
        }
    )
    return result


__all__ = ["airbyte_health", "airbyte_staging_materialization"]
