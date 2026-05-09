"""Dagster assets for Airbyte control-plane visibility and materialization."""
from __future__ import annotations

from typing import Any

from dagster import Field, Permissive, asset

from aqp.dagster.resources import AqpAirbyteResource, AqpEngineResource

_AIRBYTE_STAGING_CONFIG: dict[str, Any] = {
    "manifest": Field(
        Permissive(),
        is_required=False,
        description=(
            "PipelineManifest payload executed by AqpEngineResource. "
            "Leave empty to skip this asset run."
        ),
    )
}


@asset(
    description="Check Airbyte API health for the AQP data fabric.",
    group_name="airbyte",
    required_resource_keys={"airbyte"},
)
def airbyte_health(context) -> dict:
    airbyte: AqpAirbyteResource = context.resources.airbyte
    result = airbyte.health()
    context.add_output_metadata({"enabled": bool(result.get("ok"))})
    return result


@asset(
    description="Run a configured Airbyte staging materialization manifest through AQP.",
    group_name="airbyte",
    required_resource_keys={"engine"},
    config_schema=_AIRBYTE_STAGING_CONFIG,
)
def airbyte_staging_materialization(context) -> dict:
    """Materialize an Airbyte staging manifest when supplied via run config."""
    engine: AqpEngineResource = context.resources.engine
    manifest = (context.op_config or {}).get("manifest")
    if manifest is not None and not isinstance(manifest, dict):
        return {
            "skipped": True,
            "reason": "invalid_manifest",
            "detail": "manifest must be a JSON object",
        }
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


AIRBYTE_ASSETS = [airbyte_health, airbyte_staging_materialization]


__all__ = ["AIRBYTE_ASSETS", "airbyte_health", "airbyte_staging_materialization"]
