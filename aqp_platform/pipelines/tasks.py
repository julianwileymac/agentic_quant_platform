"""Task implementations shared by Argo templates and Dagster assets."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .config import PipelineConfig
from .metadata import emit_minio_object, emit_pipeline_run
from .minio_io import get_bytes, get_minio_client, put_bytes, put_json
from .postgres_io import (
    ensure_pipeline_tables,
    get_watermark,
    insert_vector_audit,
    is_safe_identifier,
    update_watermark,
    upsert_cdc_payload,
)
from .sources import fetch_filesystem, fetch_http, fetch_rest, fetch_s3
from .vector_io import build_chunk_records, upsert_chromadb, upsert_milvus

logger = logging.getLogger(__name__)

# Make get_tracer importable from this module so each task function can wrap
# its work in a span without importing the SDK directly (keeps the dependency
# soft-optional via the SDK's no-op fallback).
try:
    from rpi_k8s_sdk.tracing import configure_tracing as _configure_tracing
    from rpi_k8s_sdk.tracing import get_tracer
except ImportError:  # pragma: no cover - SDK missing in slim builds
    def get_tracer(name: str = "pipelines.tasks"):
        class _NoopSpan:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def set_attribute(self, *_args, **_kwargs):
                return None

        class _NoopTracer:
            def start_as_current_span(self, *_args, **_kwargs):
                return _NoopSpan()

        return _NoopTracer()

    _configure_tracing = None
else:
    try:
        _configure_tracing(
            service_name=os.environ.get("OTEL_SERVICE_NAME", "pipelines-tasks"),
            namespace="mlops",
            instrument_kafka=False,
            instrument_httpx=True,
        )
    except Exception:  # pragma: no cover - tracing must never break worker boot
        logger.exception("rpi_k8s_sdk tracing bootstrap failed; continuing without OTel")

tracer = get_tracer("pipelines.tasks")


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _guess_extension(content_type: str, source_uri: str) -> str:
    lower_uri = source_uri.lower()
    if lower_uri.endswith(".json") or "json" in content_type:
        return ".json"
    if lower_uri.endswith(".csv") or "csv" in content_type:
        return ".csv"
    if lower_uri.endswith(".parquet") or "parquet" in content_type:
        return ".parquet"
    return ".bin"


def _parse_s3_uri(source_uri: str) -> tuple[str, str]:
    parsed = urlparse(source_uri)
    if parsed.scheme != "s3":
        raise ValueError("S3 source_uri must use s3://bucket/key format")
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        raise ValueError("S3 source_uri must include both bucket and key")
    return bucket, key


def _safe_json_load(text: str) -> Any:
    return json.loads(text)


def _extract_records_from_payload(payload: bytes) -> list[dict[str, Any]]:
    text = payload.decode("utf-8", errors="replace").strip()
    if not text:
        return []
    try:
        parsed = _safe_json_load(text)
    except json.JSONDecodeError:
        return [{"raw_text": text}]
    if isinstance(parsed, list):
        return [item if isinstance(item, dict) else {"value": item} for item in parsed]
    if isinstance(parsed, dict):
        return [parsed]
    return [{"value": parsed}]


def _load_records_to_postgres(
    conn: psycopg.Connection[Any],
    table_name: str,
    records: list[dict[str, Any]],
    source_key: str,
) -> int:
    if not is_safe_identifier(table_name):
        raise ValueError(f"Unsafe table name: {table_name}")

    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {} (
                    id BIGSERIAL PRIMARY KEY,
                    source_key TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            ).format(sql.Identifier(table_name))
        )
        for record in records:
            cur.execute(
                sql.SQL("INSERT INTO {} (source_key, payload) VALUES (%s, %s::jsonb)").format(
                    sql.Identifier(table_name)
                ),
                (source_key, json.dumps(record)),
            )
    conn.commit()
    return len(records)


def run_raw_ingest(
    config: PipelineConfig,
    source_type: str,
    source_name: str,
    source_uri: str,
    output_prefix: str = "raw",
    target_bucket: str | None = None,
    rest_method: str = "GET",
    rest_body_json: str | None = None,
) -> dict[str, Any]:
    source_type = source_type.lower().strip()
    if source_type == "http":
        payload = fetch_http(source_uri, auth_header=config.http_auth_header or None)
    elif source_type == "rest":
        parsed_body = json.loads(rest_body_json) if rest_body_json else None
        payload = fetch_rest(
            url=source_uri,
            method=rest_method,
            token=config.rest_api_token or None,
            body=parsed_body,
        )
    elif source_type == "s3":
        bucket, key = _parse_s3_uri(source_uri)
        payload = fetch_s3(config=config, bucket=bucket, key=key)
    elif source_type == "filesystem":
        payload = fetch_filesystem(source_uri)
    else:
        raise ValueError(f"Unsupported source_type: {source_type}")

    timestamp = _utc_now()
    sha = __import__("hashlib").sha256(payload.body).hexdigest()
    extension = _guess_extension(payload.content_type, source_uri)
    bucket = target_bucket or config.minio_bucket_raw
    object_key = (
        f"{output_prefix}/{source_name}/{timestamp:%Y/%m/%d}/"
        f"{timestamp:%H%M%S}_{sha[:16]}{extension}"
    )

    client = get_minio_client(config)
    metadata = {
        "source_type": source_type,
        "source_name": source_name,
        "source_uri": source_uri,
        "sha256": sha,
        "ingested_at": timestamp.isoformat(),
    }
    put_bytes(
        client=client,
        bucket=bucket,
        key=object_key,
        payload=payload.body,
        content_type=payload.content_type,
        metadata=metadata,
    )
    put_json(client=client, bucket=bucket, key=f"{object_key}.metadata.json", payload=metadata)
    emit_minio_object(
        config,
        bucket=bucket,
        key=object_key,
        properties={
            **metadata,
            "content_type": payload.content_type,
            "size_bytes": len(payload.body),
            "description": f"Raw ingest output for {source_name}",
        },
    )
    emit_pipeline_run(
        config,
        name=f"raw-ingest/{source_name}",
        properties={
            "source_type": source_type,
            "source_uri": source_uri,
            "bucket": bucket,
            "object_key": object_key,
            "status": "ok",
        },
    )

    return {
        "status": "ok",
        "source_type": source_type,
        "bucket": bucket,
        "object_key": object_key,
        "sha256": sha,
        "size_bytes": len(payload.body),
    }


def run_heavy_transform(
    config: PipelineConfig,
    source_key: str,
    source_bucket: str | None = None,
    target_bucket: str | None = None,
    output_prefix: str = "processed",
    transform_mode: str = "normalize-json",
    target_table: str | None = None,
) -> dict[str, Any]:
    source_bucket_name = source_bucket or config.minio_bucket_raw
    target_bucket_name = target_bucket or config.minio_bucket_processed
    minio = get_minio_client(config)
    source_bytes = get_bytes(client=minio, bucket=source_bucket_name, key=source_key)
    source_text = source_bytes.decode("utf-8", errors="replace")

    if transform_mode == "uppercase":
        transformed_text = source_text.upper()
    elif transform_mode == "lowercase":
        transformed_text = source_text.lower()
    else:
        records = _extract_records_from_payload(source_bytes)
        transformed_text = json.dumps(records, indent=2)

    transformed_bytes = transformed_text.encode("utf-8")
    transformed_sha = __import__("hashlib").sha256(transformed_bytes).hexdigest()
    timestamp = _utc_now()
    output_key = (
        f"{output_prefix}/{timestamp:%Y/%m/%d}/"
        f"{os.path.basename(source_key)}_{transform_mode}_{transformed_sha[:12]}.json"
    )

    put_bytes(
        client=minio,
        bucket=target_bucket_name,
        key=output_key,
        payload=transformed_bytes,
        content_type="application/json",
        metadata={
            "source_key": source_key,
            "transform_mode": transform_mode,
            "transformed_at": timestamp.isoformat(),
        },
    )

    loaded_rows = 0
    if target_table:
        with psycopg.connect(config.postgres_dsn) as conn:
            loaded_rows = _load_records_to_postgres(
                conn=conn,
                table_name=target_table,
                records=_extract_records_from_payload(transformed_bytes),
                source_key=output_key,
            )
    emit_minio_object(
        config,
        bucket=target_bucket_name,
        key=output_key,
        properties={
            "source_bucket": source_bucket_name,
            "source_key": source_key,
            "transform_mode": transform_mode,
            "target_table": target_table or "",
            "loaded_rows": loaded_rows,
            "description": "Transformed pipeline output",
        },
    )

    return {
        "status": "ok",
        "source_key": source_key,
        "output_key": output_key,
        "source_bucket": source_bucket_name,
        "target_bucket": target_bucket_name,
        "loaded_rows": loaded_rows,
    }


def run_minio_to_postgres(
    config: PipelineConfig,
    source_key: str,
    source_bucket: str | None = None,
    target_table: str = "pipeline_curated_records",
) -> dict[str, Any]:
    bucket = source_bucket or config.minio_bucket_processed
    minio = get_minio_client(config)
    payload = get_bytes(minio, bucket=bucket, key=source_key)
    records = _extract_records_from_payload(payload)
    with psycopg.connect(config.postgres_dsn) as conn:
        loaded = _load_records_to_postgres(
            conn=conn,
            table_name=target_table,
            records=records,
            source_key=source_key,
        )
    return {
        "status": "ok",
        "source_bucket": bucket,
        "source_key": source_key,
        "target_table": target_table,
        "loaded_rows": loaded,
    }


def run_vector_sync(
    config: PipelineConfig,
    source_key: str,
    source_bucket: str | None = None,
    collection_name: str = "pipeline_documents",
    pipeline_name: str = "vector-sync",
    text_field: str = "text",
) -> dict[str, Any]:
    bucket = source_bucket or config.minio_bucket_processed
    minio = get_minio_client(config)
    payload = get_bytes(client=minio, bucket=bucket, key=source_key)
    records = _extract_records_from_payload(payload)

    if records and text_field in records[0]:
        all_text = "\n".join(str(item.get(text_field, "")) for item in records)
    else:
        all_text = payload.decode("utf-8", errors="replace")

    chunk_records = build_chunk_records(source_key=source_key, text=all_text)
    chroma_count = upsert_chromadb(
        host=config.chroma_host,
        port=config.chroma_port,
        collection_name=collection_name,
        records=chunk_records,
    )
    milvus_count = upsert_milvus(
        host=config.milvus_host,
        port=config.milvus_port,
        collection_name=collection_name,
        records=chunk_records,
    )

    with psycopg.connect(config.postgres_dsn) as conn:
        ensure_pipeline_tables(conn)
        for record in chunk_records:
            insert_vector_audit(
                conn=conn,
                pipeline_name=pipeline_name,
                source_key=source_key,
                chunk_id=record["id"],
                sink_name="chromadb",
            )
            insert_vector_audit(
                conn=conn,
                pipeline_name=pipeline_name,
                source_key=source_key,
                chunk_id=record["id"],
                sink_name="milvus",
            )

    return {
        "status": "ok",
        "source_key": source_key,
        "collection_name": collection_name,
        "chunk_count": len(chunk_records),
        "chromadb_upserts": chroma_count,
        "milvus_upserts": milvus_count,
    }


def run_cdc_sync(
    config: PipelineConfig,
    pipeline_name: str,
    source_table: str,
    primary_key: str = "id",
    updated_at_column: str = "updated_at",
    batch_size: int = 500,
    output_prefix: str = "cdc",
    output_bucket: str | None = None,
) -> dict[str, Any]:
    if not is_safe_identifier(source_table):
        raise ValueError(f"Unsafe source_table identifier: {source_table}")
    if not is_safe_identifier(primary_key):
        raise ValueError(f"Unsafe primary_key identifier: {primary_key}")
    if not is_safe_identifier(updated_at_column):
        raise ValueError(f"Unsafe updated_at_column identifier: {updated_at_column}")

    sink_dsn = config.postgres_dsn
    source_dsn = config.effective_source_postgres_dsn
    bucket = output_bucket or config.minio_bucket_processed
    minio = get_minio_client(config)

    with psycopg.connect(sink_dsn) as sink_conn, psycopg.connect(source_dsn) as source_conn:
        ensure_pipeline_tables(sink_conn)
        watermark = get_watermark(sink_conn, pipeline_name=pipeline_name)

        query = sql.SQL(
            "SELECT * FROM {} WHERE {} > %s ORDER BY {} ASC LIMIT %s"
        ).format(
            sql.Identifier(source_table),
            sql.Identifier(updated_at_column),
            sql.Identifier(updated_at_column),
        )
        with source_conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (watermark, batch_size))
            rows = [dict(row) for row in cur.fetchall()]

        if not rows:
            return {
                "status": "ok",
                "pipeline_name": pipeline_name,
                "source_table": source_table,
                "row_count": 0,
                "watermark": watermark.isoformat(),
            }

        max_watermark = watermark
        for row in rows:
            source_pk = str(row.get(primary_key))
            source_updated_at = row.get(updated_at_column)
            if source_updated_at and source_updated_at > max_watermark:
                max_watermark = source_updated_at
            upsert_cdc_payload(
                conn=sink_conn,
                pipeline_name=pipeline_name,
                source_table=source_table,
                source_pk=source_pk,
                payload=row,
                source_updated_at=source_updated_at,
            )

        timestamp = _utc_now()
        object_key = f"{output_prefix}/{source_table}/{timestamp:%Y/%m/%d/%H%M%S}.jsonl"
        payload = b"\n".join(
            json.dumps(row, default=str, sort_keys=True).encode("utf-8") for row in rows
        )
        put_bytes(
            client=minio,
            bucket=bucket,
            key=object_key,
            payload=payload,
            content_type="application/json",
            metadata={
                "pipeline_name": pipeline_name,
                "source_table": source_table,
                "row_count": str(len(rows)),
            },
        )

        update_watermark(sink_conn, pipeline_name=pipeline_name, watermark=max_watermark)

    return {
        "status": "ok",
        "pipeline_name": pipeline_name,
        "source_table": source_table,
        "row_count": len(rows),
        "object_key": object_key,
        "bucket": bucket,
        "new_watermark": max_watermark.isoformat(),
    }


def submit_argo_workflow_from_template(
    template_name: str,
    namespace: str,
    parameters: dict[str, str] | None = None,
    wait_for_completion: bool = True,
    poll_seconds: int = 10,
    timeout_seconds: int = 1200,
) -> dict[str, Any]:
    from kubernetes import client, config

    try:
        config.load_incluster_config()
    except Exception:
        config.load_kube_config()

    body = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Workflow",
        "metadata": {"generateName": f"{template_name}-"},
        "spec": {
            "workflowTemplateRef": {"name": template_name},
            "arguments": {
                "parameters": [
                    {"name": key, "value": str(value)}
                    for key, value in (parameters or {}).items()
                ]
            },
        },
    }
    api = client.CustomObjectsApi()
    created = api.create_namespaced_custom_object(
        group="argoproj.io",
        version="v1alpha1",
        namespace=namespace,
        plural="workflows",
        body=body,
    )
    workflow_name = created["metadata"]["name"]

    if not wait_for_completion:
        return {"status": "submitted", "workflow_name": workflow_name}

    start = time.time()
    while time.time() - start < timeout_seconds:
        workflow = api.get_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace=namespace,
            plural="workflows",
            name=workflow_name,
        )
        phase = workflow.get("status", {}).get("phase", "")
        if phase in {"Succeeded", "Failed", "Error"}:
            return {"status": phase.lower(), "workflow_name": workflow_name}
        time.sleep(poll_seconds)

    raise TimeoutError(f"Workflow {workflow_name} did not finish within {timeout_seconds}s")

