"""Discover-and-stream a directory tree as Arrow batches.

Delegates to :func:`aqp.data.pipelines.discovery.discover_datasets` so
the legacy walker (subdir disambig, browser-style ``(N)`` suffix
collapse, ``__assets__`` family for non-tabular files) keeps working
under the new engine.
"""
from __future__ import annotations

import logging
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
    "source.local_directory",
    display_name="Local Directory",
    kind=FetcherKind.LOCAL,
    description="Discover a directory tree and stream every member as Arrow batches.",
    capabilities=(
        FetcherCapability.SUPPORTS_INCREMENTAL.value,
        FetcherCapability.SUPPORTS_PARALLELISM.value,
    ),
    domains=("local.directory",),
)
class DirectoryFetcher(Fetcher):
    """Walk a directory and yield every tabular member's batches.

    ``family_filter`` (optional) limits to specific discovered family
    keys. ``max_files`` (optional) caps the count for previews.
    """

    capabilities = (FetcherCapability.SUPPORTS_INCREMENTAL,)

    def __init__(
        self,
        *,
        path: str | Path,
        family_filter: list[str] | None = None,
        max_files: int | None = None,
        chunk_rows: int = 50_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        self.path = Path(path).expanduser()
        self.family_filter = list(family_filter or [])
        self.max_files = max_files
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        return str(self.path)

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        from aqp.data.pipelines.discovery import discover_datasets

        if not self.path.exists():
            raise FileNotFoundError(f"DirectoryFetcher: {self.path} not found")

        datasets = discover_datasets(self.path)
        emitted = 0
        for ds in datasets:
            if ds.family == "__assets__":
                continue
            if self.family_filter and ds.family not in self.family_filter:
                continue

            members = list(ds.members or [])
            for member in members:
                if self.max_files is not None and emitted >= self.max_files:
                    return
                emitted += 1
                target = Path(getattr(member, "path", "") or "")
                if not target.exists():
                    continue
                ctx.emit("source", f"reading {target}")
                fetcher = FileFetcher(
                    path=target,
                    chunk_rows=self.chunk_rows,
                )
                fetcher.open(ctx)
                try:
                    yield from fetcher.fetch(ctx)
                finally:
                    fetcher.close(ctx)
