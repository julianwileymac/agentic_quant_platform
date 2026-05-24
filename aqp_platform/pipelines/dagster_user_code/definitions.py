"""Dagster definitions for pipeline orchestrator MVP."""

from __future__ import annotations

import logging
import os

from dagster import Definitions, ScheduleDefinition, define_asset_job

logger = logging.getLogger(__name__)

# Bootstrap OpenTelemetry tracing as soon as the user-code module is imported
# by the Dagster gRPC server.  The SDK helper is soft-optional - if the
# rpi_k8s_sdk package is not installed in the user-code image we silently
# fall back to no-op tracing rather than crash the user-code server.
try:
    from rpi_k8s_sdk.tracing import configure_tracing as _configure_tracing

    _configure_tracing(
        service_name=os.environ.get("OTEL_SERVICE_NAME", "dagster-user-code"),
        namespace="mlops",
        instrument_kafka=False,
        instrument_httpx=True,
    )
except Exception:  # pragma: no cover - tracing must never break the user-code server
    logger.exception("rpi_k8s_sdk tracing bootstrap failed; continuing without OTel")

from .aqp_alphavantage_assets import (
    aqp_alphavantage_intraday_delta,
    aqp_alphavantage_intraday_plan,
)
from .asset_checks import ALL_ASSET_CHECKS
from .assets import (
    cdc_incremental_sync,
    hybrid_argo_heavy_transform,
    minio_to_postgres_curated,
    vectorize_to_milvus_chroma,
)
from .datahub_assets import (
    datahub_api_sources,
    datahub_lakehouse_sources,
    datahub_metadata_bridge,
    datahub_mlflow_sources,
    datahub_platform_sources,
)
from .rag_assets import (
    graphrag_knowledge_base,
    ingest_csv_data,
    ingest_pdf_documents,
)

minio_to_postgres_job = define_asset_job(
    name="minio_to_postgres_job",
    selection=[minio_to_postgres_curated],
)

vectorization_job = define_asset_job(
    name="vectorization_job",
    selection=[vectorize_to_milvus_chroma],
)

cdc_job = define_asset_job(
    name="cdc_job",
    selection=[cdc_incremental_sync],
)

hybrid_transform_job = define_asset_job(
    name="hybrid_transform_job",
    selection=[hybrid_argo_heavy_transform],
)

cdc_hourly_schedule = ScheduleDefinition(
    name="cdc_hourly_schedule",
    cron_schedule="15 * * * *",
    job=cdc_job,
    run_config={
        "ops": {
            "cdc_incremental_sync": {
                "config": {
                    "pipeline_name": "cdc-source-events",
                    "source_table": "source_events",
                    "primary_key": "id",
                    "updated_at_column": "updated_at",
                    "batch_size": 500,
                    "output_prefix": "cdc/hourly",
                    "output_bucket": "dagster-artifacts",
                }
            }
        }
    },
)

vector_daily_schedule = ScheduleDefinition(
    name="vector_daily_schedule",
    cron_schedule="0 2 * * *",
    job=vectorization_job,
    run_config={
        "ops": {
            "vectorize_to_milvus_chroma": {
                "config": {
                    "source_key": "processed/heavy/sample.json",
                    "source_bucket": "dagster-artifacts",
                    "collection_name": "pipeline_documents",
                    "pipeline_name": "vector-sync",
                    "text_field": "text",
                }
            }
        }
    },
)

pdf_ingest_job = define_asset_job(
    name="pdf_ingest_job",
    selection=[ingest_pdf_documents],
)

csv_ingest_job = define_asset_job(
    name="csv_ingest_job",
    selection=[ingest_csv_data],
)

graphrag_job = define_asset_job(
    name="graphrag_job",
    selection=[graphrag_knowledge_base],
)

datahub_lakehouse_job = define_asset_job(
    name="datahub_lakehouse_job",
    selection=[datahub_lakehouse_sources],
)

datahub_mlflow_job = define_asset_job(
    name="datahub_mlflow_job",
    selection=[datahub_mlflow_sources],
)

datahub_platform_job = define_asset_job(
    name="datahub_platform_job",
    selection=[datahub_platform_sources],
)

datahub_api_job = define_asset_job(
    name="datahub_api_job",
    selection=[datahub_api_sources],
)

datahub_full_sync_job = define_asset_job(
    name="datahub_full_sync_job",
    selection=[
        datahub_lakehouse_sources,
        datahub_mlflow_sources,
        datahub_platform_sources,
        datahub_api_sources,
        datahub_metadata_bridge,
    ],
)

datahub_daily_schedule = ScheduleDefinition(
    name="datahub_daily_schedule",
    cron_schedule="30 3 * * *",
    job=datahub_full_sync_job,
)

aqp_alphavantage_intraday_plan_job = define_asset_job(
    name="aqp_alphavantage_intraday_plan_job",
    selection=[aqp_alphavantage_intraday_plan],
)

aqp_alphavantage_intraday_delta_job = define_asset_job(
    name="aqp_alphavantage_intraday_delta_job",
    selection=[aqp_alphavantage_intraday_delta],
)

aqp_alphavantage_intraday_delta_schedule = ScheduleDefinition(
    name="aqp_alphavantage_intraday_delta_schedule",
    cron_schedule="20 * * * *",
    job=aqp_alphavantage_intraday_delta_job,
)

defs = Definitions(
    assets=[
        aqp_alphavantage_intraday_plan,
        aqp_alphavantage_intraday_delta,
        minio_to_postgres_curated,
        vectorize_to_milvus_chroma,
        cdc_incremental_sync,
        hybrid_argo_heavy_transform,
        ingest_pdf_documents,
        ingest_csv_data,
        graphrag_knowledge_base,
        datahub_lakehouse_sources,
        datahub_mlflow_sources,
        datahub_platform_sources,
        datahub_api_sources,
        datahub_metadata_bridge,
    ],
    asset_checks=ALL_ASSET_CHECKS,
    jobs=[
        minio_to_postgres_job,
        vectorization_job,
        cdc_job,
        hybrid_transform_job,
        pdf_ingest_job,
        csv_ingest_job,
        graphrag_job,
        datahub_lakehouse_job,
        datahub_mlflow_job,
        datahub_platform_job,
        datahub_api_job,
        datahub_full_sync_job,
        aqp_alphavantage_intraday_plan_job,
        aqp_alphavantage_intraday_delta_job,
    ],
    schedules=[
        cdc_hourly_schedule,
        vector_daily_schedule,
        datahub_daily_schedule,
        aqp_alphavantage_intraday_delta_schedule,
    ],
)

