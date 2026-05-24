"""MinIO/S3 client helpers for local lab sessions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from .access import LocalAccessSettings, load_settings


@dataclass(slots=True)
class MinioObject:
    bucket: str
    key: str
    size_bytes: int | None = None
    etag: str | None = None


class MinioClient:
    """Small boto3 wrapper with defaults that match the lab ingress."""

    def __init__(self, settings: LocalAccessSettings | None = None, client: Any | None = None):
        self.settings = settings or load_settings()
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - depends on optional extra
                raise RuntimeError("Install rpi_k8s_sdk[storage] to use MinIO helpers") from exc
            self._client = boto3.client(
                "s3",
                endpoint_url=self.settings.minio_endpoint,
                aws_access_key_id=self.settings.minio_access_key,
                aws_secret_access_key=self.settings.minio_secret_key,
                region_name=self.settings.minio_region,
            )
        return self._client

    def health(self) -> dict[str, Any]:
        response = self.client.list_buckets()
        return {
            "endpoint": self.settings.minio_endpoint,
            "bucket_count": len(response.get("Buckets", [])),
            "buckets": [bucket["Name"] for bucket in response.get("Buckets", [])],
        }

    def ensure_bucket(self, bucket: str) -> None:
        try:
            self.client.head_bucket(Bucket=bucket)
        except Exception:  # noqa: BLE001 - boto3 raises several provider-specific errors
            self.client.create_bucket(Bucket=bucket)

    def upload_file(self, bucket: str, key: str, path: str | Path, *, content_type: str | None = None) -> MinioObject:
        self.ensure_bucket(bucket)
        extra_args = {"ContentType": content_type} if content_type else None
        self.client.upload_file(str(path), bucket, key, ExtraArgs=extra_args or {})
        size = Path(path).stat().st_size
        return MinioObject(bucket=bucket, key=key, size_bytes=size)

    def upload_fileobj(
        self,
        bucket: str,
        key: str,
        body: BinaryIO,
        *,
        content_type: str = "application/octet-stream",
    ) -> MinioObject:
        self.ensure_bucket(bucket)
        self.client.upload_fileobj(body, bucket, key, ExtraArgs={"ContentType": content_type})
        return MinioObject(bucket=bucket, key=key)

    def put_bytes(
        self,
        bucket: str,
        key: str,
        payload: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> MinioObject:
        self.ensure_bucket(bucket)
        response = self.client.put_object(
            Bucket=bucket,
            Key=key,
            Body=payload,
            ContentType=content_type,
            Metadata=metadata or {},
        )
        return MinioObject(
            bucket=bucket,
            key=key,
            size_bytes=len(payload),
            etag=response.get("ETag"),
        )

    def download_bytes(self, bucket: str, key: str) -> bytes:
        response = self.client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()
