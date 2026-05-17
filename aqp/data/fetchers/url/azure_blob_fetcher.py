"""Stream Arrow batches from an Azure Blob Storage object."""
from __future__ import annotations

import logging
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
    "source.azure_blob",
    display_name="Azure Blob Storage",
    kind=FetcherKind.URL,
    description="Fetch an Azure blob and stream as Arrow batches.",
    capabilities=(FetcherCapability.SUPPORTS_INCREMENTAL.value,),
    domains=("url.azure",),
    auth_type="connection_string",
)
class AzureBlobFetcher(Fetcher):
    """Download an Azure blob and stream as Arrow batches."""

    def __init__(
        self,
        *,
        container: str,
        blob: str,
        connection_string: str | None = None,
        account_url: str | None = None,
        sas_token: str | None = None,
        format: str | None = None,
        chunk_rows: int = 50_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        self.container = container
        self.blob = blob
        self.connection_string = connection_string
        self.account_url = account_url
        self.sas_token = sas_token
        self.format = (format or "").lower() or None
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        if self.account_url:
            return f"{self.account_url.rstrip('/')}/{self.container}/{self.blob}"
        return f"azure://{self.container}/{self.blob}"

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        try:
            from azure.storage.blob import BlobServiceClient
        except Exception as exc:  # noqa: BLE001 - optional dep
            raise RuntimeError(
                f"AzureBlobFetcher requires azure-storage-blob: {exc}"
            ) from exc

        if self.connection_string:
            service = BlobServiceClient.from_connection_string(self.connection_string)
        elif self.account_url:
            service = BlobServiceClient(
                account_url=self.account_url,
                credential=self.sas_token,
            )
        else:
            raise ValueError(
                "AzureBlobFetcher: connection_string or account_url required"
            )

        client = service.get_blob_client(container=self.container, blob=self.blob)
        ext = self.format or Path(self.blob).suffix.lstrip(".") or "parquet"
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as fh:
            target = Path(fh.name)
        try:
            ctx.emit("source", f"azure://{self.container}/{self.blob}")
            with target.open("wb") as outfile:
                outfile.write(client.download_blob().readall())
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
