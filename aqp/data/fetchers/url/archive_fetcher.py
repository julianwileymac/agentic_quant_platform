"""Stream Arrow batches from a remote zip / tar / tar.gz archive."""
from __future__ import annotations

import io
import logging
import tarfile
import tempfile
import zipfile
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
    "source.archive",
    display_name="Remote Archive (zip/tar/tar.gz)",
    kind=FetcherKind.URL,
    description="Fetch a remote archive, expand it, and stream every member as Arrow batches.",
    capabilities=(FetcherCapability.SUPPORTS_INCREMENTAL.value,),
    domains=("url.archive",),
)
class ArchiveFetcher(Fetcher):
    """Download an archive and stream member files as Arrow batches.

    ``url`` is downloaded to a tempfile, then expanded under another
    tempdir. Each tabular member is consumed via :class:`FileFetcher`.
    Supports zip / tar / tar.gz / tgz / tar.bz2 / tbz2 archives.
    """

    capabilities = (FetcherCapability.SUPPORTS_INCREMENTAL,)

    def __init__(
        self,
        *,
        url: str,
        member_glob: str | None = None,
        chunk_rows: int = 50_000,
        format: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        self.url = url
        self.member_glob = member_glob
        self.format = (format or "").lower() or None
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        return self.url

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        try:
            import httpx
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"ArchiveFetcher requires httpx: {exc}") from exc

        suffix = Path(urlparse(self.url).path).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".bin") as fh:
            target = Path(fh.name)
        try:
            ctx.emit("source", f"download archive {self.url}")
            with httpx.Client(timeout=300.0, follow_redirects=True) as client:
                with client.stream("GET", self.url) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        if chunk:
                            with target.open("ab") as fh2:
                                fh2.write(chunk)
            with tempfile.TemporaryDirectory() as tmpdir:
                tmppath = Path(tmpdir)
                self._extract(target, tmppath)
                yield from self._iter_members(tmppath, ctx)
        finally:
            target.unlink(missing_ok=True)

    def _extract(self, archive: Path, target_dir: Path) -> None:
        suffixes = "".join(archive.suffixes).lower()
        if suffixes.endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(target_dir)
            return
        if suffixes.endswith((".tar.gz", ".tgz")):
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(target_dir)
            return
        if suffixes.endswith((".tar.bz2", ".tbz2")):
            with tarfile.open(archive, "r:bz2") as tf:
                tf.extractall(target_dir)
            return
        if suffixes.endswith(".tar"):
            with tarfile.open(archive, "r:") as tf:
                tf.extractall(target_dir)
            return
        raise ValueError(f"ArchiveFetcher: unsupported archive {archive.name!r}")

    def _iter_members(
        self,
        target_dir: Path,
        ctx: NodeContext,
    ) -> Iterator[pa.RecordBatch]:
        if self.member_glob:
            members = sorted(target_dir.rglob(self.member_glob))
        else:
            members = sorted(p for p in target_dir.rglob("*") if p.is_file())
        for member in members:
            if not member.is_file():
                continue
            ctx.emit("source", f"reading member {member.name}")
            try:
                file_fetcher = FileFetcher(
                    path=member,
                    format=self.format,
                    chunk_rows=self.chunk_rows,
                )
                file_fetcher.open(ctx)
                try:
                    yield from file_fetcher.fetch(ctx)
                finally:
                    file_fetcher.close(ctx)
            except Exception as exc:  # noqa: BLE001 - skip non-tabular members
                logger.debug("ArchiveFetcher skipping %s: %s", member, exc)
                continue
