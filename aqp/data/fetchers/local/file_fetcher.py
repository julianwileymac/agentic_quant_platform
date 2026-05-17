"""Stream Arrow batches from a local file (parquet/csv/jsonl/arrow)."""
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

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


_PARQUET = {".parquet", ".pq"}
_CSV = {".csv"}
_TSV = {".tsv"}
_JSONL = {".jsonl", ".ndjson"}
_JSON = {".json"}
_ARROW = {".arrow", ".feather"}


@register_source_fetcher(
    "source.local_file",
    display_name="Local File",
    kind=FetcherKind.LOCAL,
    description="Stream a local parquet/csv/jsonl/arrow file as Arrow batches.",
    capabilities=(FetcherCapability.SUPPORTS_INCREMENTAL.value,),
    domains=("local.file",),
)
class FileFetcher(Fetcher):
    """Stream a single file path as Arrow batches.

    ``format`` defaults to extension-based detection but can be forced
    to ``parquet`` / ``csv`` / ``tsv`` / ``jsonl`` / ``json`` /
    ``arrow``. ``chunk_rows`` controls how many rows go into one batch.
    """

    capabilities = (FetcherCapability.SUPPORTS_INCREMENTAL,)

    def __init__(
        self,
        *,
        path: str | Path,
        format: str | None = None,
        chunk_rows: int = 50_000,
        csv_options: dict[str, Any] | None = None,
        json_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        self.path = Path(path).expanduser()
        self.format = (format or "").lower() or None
        self.csv_options = dict(csv_options or {})
        self.json_options = dict(json_options or {})
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        return str(self.path)

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        if not self.path.exists():
            raise FileNotFoundError(f"FileFetcher: {self.path} not found")

        fmt = self.format or self._detect_format(self.path)
        if fmt == "parquet":
            yield from self._read_parquet(self.path)
            return
        if fmt in {"csv", "tsv"}:
            yield from self._read_csv(self.path, sep="," if fmt == "csv" else "\t")
            return
        if fmt == "jsonl":
            yield from self._read_jsonl(self.path)
            return
        if fmt == "json":
            yield from self._read_json(self.path)
            return
        if fmt == "arrow":
            yield from self._read_arrow(self.path)
            return
        raise ValueError(f"FileFetcher: unsupported format {fmt!r} for {self.path}")

    @staticmethod
    def _detect_format(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in _PARQUET:
            return "parquet"
        if suffix in _CSV:
            return "csv"
        if suffix in _TSV:
            return "tsv"
        if suffix in _JSONL:
            return "jsonl"
        if suffix in _JSON:
            return "json"
        if suffix in _ARROW:
            return "arrow"
        return suffix.lstrip(".") or "parquet"

    def _read_parquet(self, path: Path) -> Iterator[pa.RecordBatch]:
        import pyarrow.parquet as pq

        pf = pq.ParquetFile(path)
        for batch in pf.iter_batches(batch_size=self.chunk_rows):
            yield batch

    def _read_csv(self, path: Path, *, sep: str) -> Iterator[pa.RecordBatch]:
        import pyarrow.csv as pa_csv

        opts = pa_csv.ReadOptions(block_size=max(1024, self.chunk_rows * 256))
        parse = pa_csv.ParseOptions(delimiter=sep)
        reader = pa_csv.open_csv(path, read_options=opts, parse_options=parse)
        try:
            while True:
                try:
                    batch = reader.read_next_batch()
                except StopIteration:
                    break
                if batch.num_rows == 0:
                    continue
                yield batch
        finally:
            reader.close()

    def _read_jsonl(self, path: Path) -> Iterator[pa.RecordBatch]:
        import json

        import pyarrow as pa

        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception as exc:  # noqa: BLE001
                    logger.debug("jsonl parse skip: %s", exc)
                if len(rows) >= self.chunk_rows:
                    table = pa.Table.from_pylist(rows)
                    yield from table.to_batches()
                    rows = []
        if rows:
            table = pa.Table.from_pylist(rows)
            yield from table.to_batches()

    def _read_json(self, path: Path) -> Iterator[pa.RecordBatch]:
        import json

        import pyarrow as pa

        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ValueError("FileFetcher: top-level JSON must be list or dict")
        table = pa.Table.from_pylist(data)
        yield from table.to_batches()

    def _read_arrow(self, path: Path) -> Iterator[pa.RecordBatch]:
        import pyarrow as pa
        from pyarrow import ipc

        with pa.memory_map(str(path), "r") as source:
            try:
                reader = ipc.RecordBatchFileReader(source)
                for i in range(reader.num_record_batches):
                    yield reader.get_batch(i)
            except Exception:
                # fall back to streaming format
                source2 = pa.input_stream(str(path))
                stream = ipc.RecordBatchStreamReader(source2)
                for batch in stream:
                    yield batch
