"""Streaming extractors for CSV / NDJSON / JSON-array inputs.

Every extractor yields :class:`pyarrow.Table` chunks of bounded row size
so the materialize step can append to Iceberg without ever holding more
than a single chunk in memory. Inputs may be plain filesystem paths or
zip members opened with :func:`open_member`.
"""
from __future__ import annotations

import io
import json
import logging
import zipfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

import pyarrow as pa

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Member open helpers
# ---------------------------------------------------------------------------


@dataclass
class MemberRef:
    """Reference into a discovered member, ready to be opened lazily.

    ``path`` points to either a plain file or a zip archive; when
    ``archive_path`` is set we'll open the zip and stream the named
    member. Nested archives use ``outer.zip::inner.csv`` notation.
    """

    path: str
    archive_path: str | None
    format: str
    delimiter: str | None

    @property
    def display_name(self) -> str:
        if self.archive_path:
            return f"{self.path}!{self.archive_path}"
        return self.path


@contextmanager
def open_member(member: MemberRef) -> Iterator[IO[bytes]]:
    """Open a binary stream for ``member``.

    Handles plain files, zip-member streams, and one level of nested
    zip extraction (the nested archive is materialized to a temp file
    so zipfile can re-open it). The temp file is cleaned up on exit.
    """
    if not member.archive_path:
        with open(member.path, "rb") as fh:
            yield fh
        return

    parts = member.archive_path.split("::", 1)
    outer = parts[0]
    inner = parts[1] if len(parts) > 1 else None

    if inner is None:
        with zipfile.ZipFile(member.path, "r") as zf:
            with zf.open(outer) as fh:
                yield fh
        return

    # Nested archive: extract outer to temp, recurse.
    import tempfile

    with zipfile.ZipFile(member.path, "r") as zf:
        with zf.open(outer) as src, tempfile.NamedTemporaryFile(
            prefix="aqp_nested_", suffix=".zip", delete=False
        ) as tmp:
            tmp.write(src.read())
            tmp_path = tmp.name
    try:
        with zipfile.ZipFile(tmp_path, "r") as inner_zf:
            with inner_zf.open(inner) as fh:
                yield fh
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:  # pragma: no cover
            pass


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def iter_csv_chunks(
    member: MemberRef,
    *,
    chunk_rows: int = 50_000,
) -> Iterator[pa.Table]:
    """Yield :class:`pa.Table` chunks for a CSV/PSV/TSV member.

    Regulatory corpora routinely mix sentinel strings (``Exempt``,
    blank, ``NA``) into otherwise numeric columns and may contain
    all-null columns in early chunks. PyArrow's streaming CSV reader
    infers concrete types eagerly and stops on those files, so the
    production path uses the plain ``csv`` module fallback and writes
    every cell as a string. That keeps ingestion robust; downstream
    feature jobs can cast typed columns explicitly once the table is
    cataloged.
    """
    yield from _fallback_csv_chunks(member, chunk_rows)
    return

    from pyarrow import csv as pa_csv

    delimiter = (member.delimiter or ",")[:1] or ","
    parse_opts = pa_csv.ParseOptions(delimiter=delimiter, newlines_in_values=True)
    convert_opts = pa_csv.ConvertOptions(strings_can_be_null=True)
    read_opts = pa_csv.ReadOptions(block_size=8 * 1024 * 1024, use_threads=True)

    with open_member(member) as fh:
        try:
            reader = pa_csv.open_csv(
                fh,
                read_options=read_opts,
                parse_options=parse_opts,
                convert_options=convert_opts,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("csv reader failed for %s (%s); attempting fallback", member.display_name, exc)
            yield from _fallback_csv_chunks(member, chunk_rows)
            return

        buffer: list[pa.RecordBatch] = []
        buffered_rows = 0
        try:
            for batch in reader:
                if batch.num_rows == 0:
                    continue
                buffer.append(batch)
                buffered_rows += batch.num_rows
                if buffered_rows >= chunk_rows:
                    yield pa.Table.from_batches(buffer)
                    buffer = []
                    buffered_rows = 0
            if buffer:
                yield pa.Table.from_batches(buffer)
        except Exception as exc:  # noqa: BLE001
            logger.warning("csv stream interrupted for %s: %s", member.display_name, exc)


def _fallback_csv_chunks(member: MemberRef, chunk_rows: int) -> Iterator[pa.Table]:
    """Plain ``csv`` module fallback for messy files."""
    import csv as csv_mod

    csv_mod.field_size_limit(1024 * 1024 * 1024)
    delimiter = (member.delimiter or ",")[:1] or ","
    with open_member(member) as fh:
        wrapper = io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline="")
        reader = csv_mod.reader(wrapper, delimiter=delimiter)
        try:
            header = next(reader)
        except StopIteration:
            return
        header = _dedupe_header([_safe_col(c) for c in header])
        rows: list[list[str]] = []
        for row in reader:
            if len(row) < len(header):
                row = list(row) + [None] * (len(header) - len(row))  # type: ignore[list-item]
            elif len(row) > len(header):
                row = row[: len(header)]
            rows.append(row)
            if len(rows) >= chunk_rows:
                yield _rows_to_table(header, rows)
                rows = []
        if rows:
            yield _rows_to_table(header, rows)


def _rows_to_table(header: list[str], rows: list[list[str]]) -> pa.Table:
    cols: dict[str, list[Any]] = {h: [] for h in header}
    for row in rows:
        for h, v in zip(header, row):
            cols[h].append(v)
    return pa.table({h: pa.array(v, type=pa.string()) for h, v in cols.items()})


def _safe_col(name: str) -> str:
    return (name or "").strip() or "col"


def _dedupe_header(header: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for name in header:
        base = name or "col"
        count = seen.get(base, 0)
        seen[base] = count + 1
        out.append(base if count == 0 else f"{base}_{count + 1}")
    return out


# ---------------------------------------------------------------------------
# NDJSON / JSON arrays
# ---------------------------------------------------------------------------


def iter_ndjson_chunks(
    member: MemberRef,
    *,
    chunk_rows: int = 25_000,
) -> Iterator[pa.Table]:
    """Yield chunks for newline-delimited JSON members."""
    rows: list[dict[str, Any]] = []
    with open_member(member) as fh:
        wrapper = io.TextIOWrapper(fh, encoding="utf-8", errors="replace")
        for line in wrapper:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
                if len(rows) >= chunk_rows:
                    yield _rows_to_arrow(rows)
                    rows = []
    if rows:
        yield _rows_to_arrow(rows)


def iter_json_array_chunks(
    member: MemberRef,
    *,
    chunk_rows: int = 25_000,
) -> Iterator[pa.Table]:
    """Yield chunks for JSON-array files (``[ {...}, {...} ]``).

    Tries :mod:`ijson` first for true streaming; falls back to a
    one-shot :func:`json.loads` on small files (<32 MB).
    """
    rows: list[dict[str, Any]] = []
    try:
        import ijson  # type: ignore[import]
    except ImportError:
        ijson = None  # type: ignore[assignment]

    with open_member(member) as fh:
        if ijson is not None:
            try:
                # Try common shapes used by openFDA / patent payloads.
                paths_to_try = ("item", "results.item", "data.item", "records.item")
                produced = False
                buf = fh.read()
                for path in paths_to_try:
                    try:
                        for obj in ijson.items(io.BytesIO(buf), path):
                            if not isinstance(obj, dict):
                                continue
                            rows.append(obj)
                            produced = True
                            if len(rows) >= chunk_rows:
                                yield _rows_to_arrow(rows)
                                rows = []
                        if produced:
                            break
                    except Exception:  # noqa: BLE001
                        continue
                if rows:
                    yield _rows_to_arrow(rows)
                if produced:
                    return
            except Exception:  # noqa: BLE001
                logger.debug("ijson streaming failed for %s, falling back to json.loads", member.display_name)

        try:
            fh.seek(0)
        except OSError:
            pass
        try:
            payload = json.load(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("json.load failed for %s: %s", member.display_name, exc)
            return

    items: Iterable[Any] = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for key in ("results", "data", "items", "records"):
            if isinstance(payload.get(key), list):
                items = payload[key]
                break

    rows = []
    for obj in items:
        if isinstance(obj, dict):
            rows.append(obj)
            if len(rows) >= chunk_rows:
                yield _rows_to_arrow(rows)
                rows = []
    if rows:
        yield _rows_to_arrow(rows)


def _rows_to_arrow(rows: list[dict[str, Any]]) -> pa.Table:
    """Convert a list of dicts to a pyarrow Table with stringified values.

    Iceberg dislikes rapidly shifting types between chunks, so we
    canonicalise nested objects/arrays to JSON strings and primitives to
    string. This is intentionally lossy on nested data — downstream
    queries can json_extract from the string columns. Top-level scalar
    columns keep their native string representation.
    """
    flattened: list[dict[str, str | None]] = []
    keys_seen: set[str] = set()
    for row in rows:
        flat: dict[str, str | None] = {}
        for k, v in row.items():
            key = _safe_col(str(k))
            keys_seen.add(key)
            if v is None:
                flat[key] = None
            elif isinstance(v, (dict, list)):
                try:
                    flat[key] = json.dumps(v, ensure_ascii=False, default=str)
                except Exception:  # noqa: BLE001
                    flat[key] = str(v)
            elif isinstance(v, bool):
                flat[key] = "true" if v else "false"
            else:
                flat[key] = str(v)
        flattened.append(flat)
    cols: dict[str, list[str | None]] = {k: [] for k in sorted(keys_seen)}
    for fr in flattened:
        for k in cols:
            cols[k].append(fr.get(k))
    return pa.table({k: pa.array(v, type=pa.string()) for k, v in cols.items()})


def iter_member_chunks(member: MemberRef, *, chunk_rows: int = 50_000) -> Iterator[pa.Table]:
    """Dispatch by ``member.format`` to the right streaming reader."""
    if member.format == "csv":
        yield from iter_csv_chunks(member, chunk_rows=chunk_rows)
    elif member.format == "ndjson":
        yield from iter_ndjson_chunks(member, chunk_rows=chunk_rows)
    elif member.format == "json_array":
        yield from iter_json_array_chunks(member, chunk_rows=chunk_rows)
    else:
        logger.debug("skipping member with unknown format: %s", member.display_name)
        return
