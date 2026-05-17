"""Stream Arrow batches from a Google Cloud Storage object."""
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
    "source.gcs",
    display_name="Google Cloud Storage",
    kind=FetcherKind.URL,
    description="Fetch a GCS object and stream as Arrow batches.",
    capabilities=(FetcherCapability.SUPPORTS_INCREMENTAL.value,),
    domains=("url.gcs",),
    auth_type="service_account",
)
class GcsFetcher(Fetcher):
    """Download ``gs://bucket/key`` and stream as Arrow batches."""

    capabilities = (FetcherCapability.SUPPORTS_INCREMENTAL,)

    def __init__(
        self,
        *,
        url: str | None = None,
        bucket: str | None = None,
        key: str | None = None,
        project: str | None = None,
        credentials_path: str | None = None,
        format: str | None = None,
        chunk_rows: int = 50_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        if url:
            parsed = urlparse(url)
            if parsed.scheme not in {"gs", "gcs"}:
                raise ValueError(f"GcsFetcher: invalid url scheme {parsed.scheme!r}")
            bucket = bucket or parsed.netloc
            key = key or parsed.path.lstrip("/")
        if not bucket or not key:
            raise ValueError("GcsFetcher: bucket and key required")
        self.bucket = bucket
        self.key = key
        self.project = project
        self.credentials_path = credentials_path
        self.format = (format or "").lower() or None
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        return f"gs://{self.bucket}/{self.key}"

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        try:
            from google.cloud import storage
        except Exception as exc:  # noqa: BLE001 - optional dep
            raise RuntimeError(
                f"GcsFetcher requires google-cloud-storage: {exc}"
            ) from exc

        client = (
            storage.Client.from_service_account_json(self.credentials_path)
            if self.credentials_path
            else storage.Client(project=self.project) if self.project else storage.Client()
        )
        bucket = client.bucket(self.bucket)
        blob = bucket.blob(self.key)
        ext = self.format or Path(self.key).suffix.lstrip(".") or "parquet"
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as fh:
            target = Path(fh.name)
        try:
            ctx.emit("source", f"gs://{self.bucket}/{self.key}")
            blob.download_to_filename(str(target))
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
