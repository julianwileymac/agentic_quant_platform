"""Filesystem inspector for local parquet datasets.

Used by the Settings page and the backtest data-source picker to preview a
local parquet root before registering it as a data source. Reports:

- Discovered file count + total bytes
- Hive-style partition keys (``year=2024/month=01/...``)
- Column list + dtypes from a representative file
- A handful of sample rows
- Heuristic suggestions for how to map columns to ``timestamp`` / ``vt_symbol``
  / OHLCV when the dataset isn't already in the canonical shape

The inspector deliberately works **without DuckDB** for the cheap path
(file enumeration + Hive parse) and falls back to ``pyarrow.parquet`` for
schema/sample reads. DuckDB can still be invoked separately to validate
that ``read_parquet(..., hive_partitioning=true)`` succeeds.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_HIVE_RE = re.compile(r"^([A-Za-z0-9_\-]+)=([^/\\]+)$")

_COLUMN_HINTS: dict[str, list[str]] = {
    "timestamp": [
        "timestamp",
        "ts",
        "datetime",
        "date",
        "time",
        "as_of",
        "asof_date",
    ],
    "vt_symbol": [
        "vt_symbol",
        "symbol",
        "ticker",
        "instrument",
        "asset",
        "code",
    ],
    "open": ["open", "o", "open_price", "px_open"],
    "high": ["high", "h", "high_price", "px_high"],
    "low": ["low", "l", "low_price", "px_low"],
    "close": ["close", "c", "adj_close", "close_price", "px_close", "px_last"],
    "volume": ["volume", "vol", "v", "qty", "quantity"],
}


@dataclass(frozen=True)
class PartitionInfo:
    key: str
    sample_values: list[str]


@dataclass
class InspectionReport:
    path: str
    exists: bool
    file_count: int = 0
    total_bytes: int = 0
    sample_files: list[str] = field(default_factory=list)
    partition_keys: list[PartitionInfo] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    dtypes: dict[str, str] = field(default_factory=dict)
    sample_rows: list[dict[str, Any]] = field(default_factory=list)
    suggested_glob: str | None = None
    suggested_column_map: dict[str, str] = field(default_factory=dict)
    hive_partitioning: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "exists": self.exists,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "sample_files": self.sample_files,
            "partition_keys": [
                {"key": p.key, "sample_values": p.sample_values}
                for p in self.partition_keys
            ],
            "columns": self.columns,
            "dtypes": self.dtypes,
            "sample_rows": self.sample_rows,
            "suggested_glob": self.suggested_glob,
            "suggested_column_map": self.suggested_column_map,
            "hive_partitioning": self.hive_partitioning,
            "error": self.error,
        }


def _bytes_to_human(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    val = float(n)
    for unit in units:
        if val < 1024 or unit == units[-1]:
            return f"{val:.1f} {unit}"
        val /= 1024
    return f"{n} B"


def _enumerate_parquet(root: Path, *, max_files: int = 5000) -> list[Path]:
    """Walk ``root`` for ``*.parquet`` and ``*.parq`` files (capped)."""
    files: list[Path] = []
    if not root.exists():
        return files
    for path in root.rglob("*.parquet"):
        files.append(path)
        if len(files) >= max_files:
            break
    if len(files) < max_files:
        for path in root.rglob("*.parq"):
            files.append(path)
            if len(files) >= max_files:
                break
    return files


def _detect_partitions(root: Path, files: list[Path]) -> tuple[list[PartitionInfo], bool]:
    """Parse ``key=value`` segments out of file paths relative to ``root``."""
    by_key: dict[str, list[str]] = {}
    hive_seen = False
    for f in files:
        try:
            rel = f.relative_to(root)
        except ValueError:
            continue
        for part in rel.parts[:-1]:
            match = _HIVE_RE.match(part)
            if match:
                hive_seen = True
                key, value = match.group(1), match.group(2)
                bucket = by_key.setdefault(key, [])
                if value not in bucket and len(bucket) < 12:
                    bucket.append(value)
    out = [PartitionInfo(key=k, sample_values=v) for k, v in sorted(by_key.items())]
    return out, hive_seen


def _suggest_column_map(columns: list[str]) -> dict[str, str]:
    """Heuristic: map our canonical names to user columns by case-insensitive hits."""
    lower = {c.lower(): c for c in columns}
    out: dict[str, str] = {}
    for canonical, hints in _COLUMN_HINTS.items():
        for hint in hints:
            if hint in lower:
                out[canonical] = lower[hint]
                break
    return out


def _read_schema_and_sample(
    files: list[Path], *, sample_rows: int = 5
) -> tuple[list[str], dict[str, str], list[dict[str, Any]], str | None]:
    """Return columns, dtypes, sample rows from the first readable file."""
    if not files:
        return [], {}, [], None
    try:
        import pyarrow.parquet as pq
    except Exception as exc:  # noqa: BLE001
        return [], {}, [], f"pyarrow unavailable: {exc}"

    target = files[0]
    try:
        pq_file = pq.ParquetFile(str(target))
        schema = pq_file.schema_arrow
        cols = [str(f.name) for f in schema]
        dtypes = {str(f.name): str(f.type) for f in schema}
        rows: list[dict[str, Any]] = []
        try:
            batch = next(pq_file.iter_batches(batch_size=max(1, sample_rows)))
            table = batch.to_pandas()
            rows = table.head(sample_rows).to_dict(orient="records")
        except StopIteration:  # pragma: no cover
            rows = []
        return cols, dtypes, rows, None
    except Exception as exc:  # noqa: BLE001
        return [], {}, [], f"could not read schema: {exc}"


def inspect_root(path: str | Path, *, max_files: int = 5000) -> InspectionReport:
    """Probe a local parquet directory and return a structured report."""
    root = Path(path).expanduser().resolve()
    if not root.exists():
        return InspectionReport(path=str(root), exists=False, error="path does not exist")

    files = _enumerate_parquet(root, max_files=max_files)
    if not files:
        return InspectionReport(
            path=str(root),
            exists=True,
            error="no parquet files found under this path",
        )

    total = sum(f.stat().st_size for f in files if f.exists())
    parts, hive_seen = _detect_partitions(root, files)
    cols, dtypes, sample, schema_err = _read_schema_and_sample(files)
    suggested_map = _suggest_column_map(cols) if cols else {}
    suggested_glob = "**/*.parquet" if hive_seen else None

    return InspectionReport(
        path=str(root),
        exists=True,
        file_count=len(files),
        total_bytes=total,
        sample_files=[str(f) for f in files[:5]],
        partition_keys=parts,
        columns=cols,
        dtypes=dtypes,
        sample_rows=sample,
        suggested_glob=suggested_glob,
        suggested_column_map=suggested_map,
        hive_partitioning=hive_seen,
        error=schema_err,
    )


def humanize(report: InspectionReport) -> str:
    """One-line summary for log/CLI output."""
    return (
        f"{report.path} | {report.file_count} files | "
        f"{_bytes_to_human(report.total_bytes)} | "
        f"hive={'yes' if report.hive_partitioning else 'no'} | "
        f"cols={len(report.columns)}"
    )


__all__ = ["InspectionReport", "PartitionInfo", "humanize", "inspect_root"]
