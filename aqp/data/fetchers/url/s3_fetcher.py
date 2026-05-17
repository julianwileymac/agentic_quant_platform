"""Stream Arrow batches from an S3 / MinIO object."""
from __future__ import annotations

import logging
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from aqp.data.engine.nodes import NodeContext
from aqp.data.fetchers.base import (
    Fetcher,
    FetcherCapability,
    FetcherKind,
    register_source_fetcher,
)
from aqp.data.fetchers.local.file_fetcher import FileFetcher

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_source_fetcher(
    "source.s3",
    display_name="Amazon S3 / MinIO",
    kind=FetcherKind.URL,
    description="Fetch an object from S3 (or S3-compatible MinIO) and stream as Arrow batches.",
    capabilities=(FetcherCapability.SUPPORTS_INCREMENTAL.value,),
    domains=("url.s3",),
    auth_type="aws_credentials",
)
class S3Fetcher(Fetcher):
    """Download ``s3://bucket/key`` and stream as Arrow batches.

    ``endpoint_url`` / ``access_key`` / ``secret_key`` / ``region``
    default to the values from :class:`aqp.config.Settings` so the
    same MinIO instance is reachable from every fetcher.
    """

    capabilities = (FetcherCapability.SUPPORTS_INCREMENTAL,)

    def __init__(
        self,
        *,
        url: str | None = None,
        bucket: str | None = None,
        key: str | None = None,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str | None = None,
        format: str | None = None,
        chunk_rows: int = 50_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        if url:
            parsed = urlparse(url)
            if parsed.scheme not in {"s3", "s3a"}:
                raise ValueError(f"S3Fetcher: invalid url scheme {parsed.scheme!r}")
            bucket = bucket or parsed.netloc
            key = key or parsed.path.lstrip("/")
        if not bucket or not key:
            raise ValueError("S3Fetcher: bucket and key required")
        self.bucket = bucket
        self.key = key
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.format = (format or "").lower() or None
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        return f"s3://{self.bucket}/{self.key}"

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        from aqp.config import settings

        try:
            import boto3
        except Exception as exc:  # noqa: BLE001 - optional dep
            raise RuntimeError(
                f"S3Fetcher requires boto3: {exc}. Install with `pip install boto3`."
            ) from exc

        client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url
            or settings.s3_endpoint_url
            or settings.minio_endpoint_url
            or None,
            aws_access_key_id=self.access_key
            or settings.s3_access_key
            or settings.minio_access_key
            or None,
            aws_secret_access_key=self.secret_key
            or settings.s3_secret_key
            or settings.minio_secret_key
            or None,
            region_name=self.region or settings.s3_region or None,
        )

        ext = self.format or Path(self.key).suffix.lstrip(".") or "parquet"
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as fh:
            target = Path(fh.name)
        try:
            ctx.emit("source", f"s3://{self.bucket}/{self.key}")
            client.download_file(self.bucket, self.key, str(target))
            file_fetcher = FileFetcher(
                path=target,
                format=ext,
                chunk_rows=self.chunk_rows,
            )
            file_fetcher.open(ctx)
            try:
                yield from file_fetcher.fetch(ctx)
            finally:
                file_fetcher.close(ctx)
        finally:
            target.unlink(missing_ok=True)
