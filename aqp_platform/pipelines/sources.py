"""Source ingestion helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .config import PipelineConfig
from .minio_io import get_source_s3_client


@dataclass(slots=True)
class SourcePayload:
    body: bytes
    content_type: str


def fetch_http(url: str, auth_header: str | None = None) -> SourcePayload:
    headers: dict[str, str] = {}
    if auth_header:
        headers["Authorization"] = auth_header
    response = requests.get(url, headers=headers, timeout=120)
    response.raise_for_status()
    return SourcePayload(
        body=response.content,
        content_type=response.headers.get("content-type", "application/octet-stream"),
    )


def fetch_rest(
    url: str,
    method: str = "GET",
    token: str | None = None,
    body: dict[str, Any] | None = None,
) -> SourcePayload:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.request(
        method=method.upper(),
        url=url,
        headers=headers,
        json=body,
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    return SourcePayload(body=json.dumps(payload).encode("utf-8"), content_type="application/json")


def fetch_s3(
    config: PipelineConfig,
    bucket: str,
    key: str,
) -> SourcePayload:
    client = get_source_s3_client(config)
    response = client.get_object(Bucket=bucket, Key=key)
    return SourcePayload(
        body=response["Body"].read(),
        content_type=response.get("ContentType", "application/octet-stream"),
    )


def fetch_filesystem(path: str) -> SourcePayload:
    file_path = Path(path)
    data = file_path.read_bytes()
    return SourcePayload(body=data, content_type="application/octet-stream")

