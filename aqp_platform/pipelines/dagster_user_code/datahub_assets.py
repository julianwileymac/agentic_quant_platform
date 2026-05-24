"""Dagster assets for orchestrating DataHub source ingestion."""

from __future__ import annotations

from dagster import Field, Failure, MetadataValue, asset


_DATAHUB_ASSET_CONFIG = {
    "namespace": Field(str, default_value="mlops"),
    "job_suffix": Field(str, default_value="dagster"),
    "wait_for_completion": Field(bool, default_value=True),
    "timeout_seconds": Field(int, default_value=2400),
}


def submit_argo_workflow_from_template(**kwargs):
    from pipelines.tasks import submit_argo_workflow_from_template

    return submit_argo_workflow_from_template(**kwargs)


def _run_datahub_group(context, source_group: str) -> dict[str, str]:
    op_config = context.op_config
    result = submit_argo_workflow_from_template(
        template_name="datahub-ingestion",
        namespace=op_config["namespace"],
        parameters={
            "source_group": source_group,
            "job_suffix": op_config["job_suffix"],
            "timeout_seconds": str(op_config["timeout_seconds"]),
        },
        wait_for_completion=op_config["wait_for_completion"],
        timeout_seconds=op_config["timeout_seconds"],
    )
    status = result.get("status", "")
    if status in {"failed", "error"}:
        raise Failure(f"DataHub {source_group} ingestion failed: {result}")

    context.add_output_metadata(
        {
            "source_group": MetadataValue.text(source_group),
            "workflow_name": MetadataValue.text(result.get("workflow_name", "")),
            "status": MetadataValue.text(status),
        }
    )
    return result


@asset(
    config_schema=_DATAHUB_ASSET_CONFIG,
    description="Ingest DataHub metadata for MinIO and Iceberg lakehouse sources.",
)
def datahub_lakehouse_sources(context):
    return _run_datahub_group(context, "lakehouse")


@asset(
    config_schema=_DATAHUB_ASSET_CONFIG,
    description="Ingest DataHub metadata for rpi and AQP MLflow sources.",
)
def datahub_mlflow_sources(context):
    return _run_datahub_group(context, "mlflow")


@asset(
    config_schema=_DATAHUB_ASSET_CONFIG,
    description="Ingest DataHub metadata for Kafka, Grafana, Flink, and Prefect platform sources.",
)
def datahub_platform_sources(context):
    return _run_datahub_group(context, "platform")


@asset(
    config_schema=_DATAHUB_ASSET_CONFIG,
    description="Ingest DataHub metadata for the Agentic Quant Platform OpenAPI surface.",
)
def datahub_api_sources(context):
    return _run_datahub_group(context, "api")


@asset(
    config_schema=_DATAHUB_ASSET_CONFIG,
    description="Emit bridge metadata for orchestration and vector-store sources.",
)
def datahub_metadata_bridge(context):
    return _run_datahub_group(context, "bridge")
