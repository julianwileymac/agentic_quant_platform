"""S3/MinIO helpers for pipeline data movement."""

from __future__ import annotations

import json
from typing import Any

import boto3
from botocore.exceptions import ClientError

from .config import PipelineConfig


def get_minio_client(config: PipelineConfig):
    return boto3.client(
        "s3",
        endpoint_url=config.minio_endpoint,
        aws_access_key_id=config.minio_access_key,
        aws_secret_access_key=config.minio_secret_key,
        region_name=config.minio_region,
    )


def get_source_s3_client(config: PipelineConfig):
    return boto3.client(
        "s3",
        endpoint_url=config.source_s3_endpoint,
        aws_access_key_id=config.source_s3_access_key,
        aws_secret_access_key=config.source_s3_secret_key,
        region_name=config.source_s3_region,
    )


def ensure_bucket(client: Any, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)


def put_bytes(
    client: Any,
    bucket: str,
    key: str,
    payload: bytes,
    content_type: str = "application/octet-stream",
    metadata: dict[str, str] | None = None,
) -> None:
    ensure_bucket(client, bucket)
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=payload,
        ContentType=content_type,
        Metadata=metadata or {},
    )


def get_bytes(client: Any, bucket: str, key: str) -> bytes:
    response = client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def put_json(client: Any, bucket: str, key: str, payload: dict[str, Any]) -> None:
    put_bytes(
        client=client,
        bucket=bucket,
        key=key,
        payload=json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
        content_type="application/json",
    )

