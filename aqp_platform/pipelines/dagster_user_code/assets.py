"""Dagster assets for ingestion, CDC, vectorization, and hybrid Argo execution."""

from __future__ import annotations

from dagster import Field, Failure, MetadataValue, asset

from pipelines.config import PipelineConfig
from pipelines.tasks import (
    run_cdc_sync,
    run_minio_to_postgres,
    run_vector_sync,
    submit_argo_workflow_from_template,
)


@asset(
    config_schema={
        "source_key": Field(str, default_value="processed/heavy/sample.json"),
        "source_bucket": Field(str, default_value="dagster-artifacts"),
        "target_table": Field(str, default_value="pipeline_curated_records"),
    },
    description="Load processed MinIO object into curated PostgreSQL table.",
)
def minio_to_postgres_curated(context):
    config = PipelineConfig()
    op_config = context.op_config
    result = run_minio_to_postgres(
        config=config,
        source_key=op_config["source_key"],
        source_bucket=op_config["source_bucket"],
        target_table=op_config["target_table"],
    )
    context.add_output_metadata(
        {
            "source_key": MetadataValue.text(result["source_key"]),
            "target_table": MetadataValue.text(result["target_table"]),
            "loaded_rows": result["loaded_rows"],
        }
    )
    return result


@asset(
    config_schema={
        "source_key": Field(str, default_value="processed/heavy/sample.json"),
        "source_bucket": Field(str, default_value="dagster-artifacts"),
        "collection_name": Field(str, default_value="pipeline_documents"),
        "pipeline_name": Field(str, default_value="vector-sync"),
        "text_field": Field(str, default_value="text"),
    },
    description="Chunk and vectorize MinIO documents to Milvus and ChromaDB.",
)
def vectorize_to_milvus_chroma(context):
    config = PipelineConfig()
    op_config = context.op_config
    result = run_vector_sync(
        config=config,
        source_key=op_config["source_key"],
        source_bucket=op_config["source_bucket"],
        collection_name=op_config["collection_name"],
        pipeline_name=op_config["pipeline_name"],
        text_field=op_config["text_field"],
    )
    context.add_output_metadata(
        {
            "collection_name": MetadataValue.text(result["collection_name"]),
            "chunk_count": result["chunk_count"],
            "milvus_upserts": result["milvus_upserts"],
            "chromadb_upserts": result["chromadb_upserts"],
        }
    )
    return result


@asset(
    config_schema={
        "pipeline_name": Field(str, default_value="cdc-source-events"),
        "source_table": Field(str, default_value="source_events"),
        "primary_key": Field(str, default_value="id"),
        "updated_at_column": Field(str, default_value="updated_at"),
        "batch_size": Field(int, default_value=500),
        "output_prefix": Field(str, default_value="cdc"),
        "output_bucket": Field(str, default_value="dagster-artifacts"),
    },
    description="Incremental CDC sync from source PostgreSQL to MinIO + sink state tables.",
)
def cdc_incremental_sync(context):
    config = PipelineConfig()
    op_config = context.op_config
    result = run_cdc_sync(
        config=config,
        pipeline_name=op_config["pipeline_name"],
        source_table=op_config["source_table"],
        primary_key=op_config["primary_key"],
        updated_at_column=op_config["updated_at_column"],
        batch_size=op_config["batch_size"],
        output_prefix=op_config["output_prefix"],
        output_bucket=op_config["output_bucket"],
    )
    context.add_output_metadata(
        {
            "pipeline_name": MetadataValue.text(result["pipeline_name"]),
            "source_table": MetadataValue.text(result["source_table"]),
            "row_count": result["row_count"],
            "object_key": MetadataValue.text(result.get("object_key", "")),
            "new_watermark": MetadataValue.text(result.get("new_watermark", "")),
        }
    )
    return result


@asset(
    deps=[minio_to_postgres_curated],
    config_schema={
        "template_name": Field(str, default_value="pipeline-heavy-transform"),
        "namespace": Field(str, default_value="mlops"),
        "source_key": Field(str, default_value="raw/sample-source/latest.json"),
        "source_bucket": Field(str, default_value="dagster-artifacts"),
        "target_bucket": Field(str, default_value="dagster-artifacts"),
        "output_prefix": Field(str, default_value="processed/heavy"),
        "transform_mode": Field(str, default_value="normalize-json"),
        "target_table": Field(str, default_value="pipeline_curated_records"),
        "wait_for_completion": Field(bool, default_value=True),
        "timeout_seconds": Field(int, default_value=1200),
    },
    description="Trigger heavy Argo WorkflowTemplate run and surface status in Dagster.",
)
def hybrid_argo_heavy_transform(context):
    op_config = context.op_config
    result = submit_argo_workflow_from_template(
        template_name=op_config["template_name"],
        namespace=op_config["namespace"],
        parameters={
            "source_key": op_config["source_key"],
            "source_bucket": op_config["source_bucket"],
            "target_bucket": op_config["target_bucket"],
            "output_prefix": op_config["output_prefix"],
            "transform_mode": op_config["transform_mode"],
            "target_table": op_config["target_table"],
        },
        wait_for_completion=op_config["wait_for_completion"],
        timeout_seconds=op_config["timeout_seconds"],
    )
    status = result.get("status", "")
    if status in {"failed", "error"}:
        raise Failure(f"Argo workflow failed: {result}")

    context.add_output_metadata(
        {
            "workflow_name": MetadataValue.text(result.get("workflow_name", "")),
            "status": MetadataValue.text(status),
        }
    )
    return result

