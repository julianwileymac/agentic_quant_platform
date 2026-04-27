"""Materialize streamed Arrow chunks into Iceberg-managed Parquet tables.

Per dataset family we:

1. Open every member with :func:`iter_member_chunks`.
2. Normalize column names to snake_case + reconcile schemas across
   chunks (we promote the first chunk's schema as the table schema and
   cast subsequent chunks to it; new columns trigger an in-place schema
   evolution via PyIceberg's :meth:`Table.update_schema` when possible).
3. Append each chunk into the Iceberg table.
4. Honor row / file caps and emit a ``truncated`` flag in the result.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import pyarrow as pa

from aqp.config import settings
from aqp.data import iceberg_catalog
from aqp.data.pipelines.discovery import DiscoveredDataset
from aqp.data.pipelines.extractors import MemberRef, iter_member_chunks

logger = logging.getLogger(__name__)


_SNAKE_RE = re.compile(r"[^a-z0-9_]+")


def _snake(name: str) -> str:
    n = (name or "").strip()
    n = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", n)
    n = re.sub(r"\s+", "_", n)
    n = _SNAKE_RE.sub("_", n.lower()).strip("_")
    return n or "col"


def _normalize_schema(schema: pa.Schema) -> tuple[pa.Schema, list[str]]:
    """Rename columns to snake_case, dedup collisions, return new schema + names."""
    seen: dict[str, int] = {}
    new_names: list[str] = []
    fields: list[pa.Field] = []
    for f in schema.names:
        s = _snake(f)
        if s in seen:
            seen[s] += 1
            s = f"{s}_{seen[s]}"
        else:
            seen[s] = 1
        new_names.append(s)
    for i in range(len(schema)):
        typ = schema.field(i).type
        # Iceberg format v2 does not support pa.null() fields. If the
        # first chunk for a column is entirely blank, promote it to
        # string immediately; later chunks can still cast concrete
        # values into that column.
        if pa.types.is_null(typ):
            typ = pa.string()
        fields.append(pa.field(new_names[i], typ))
    new_schema = pa.schema(fields)
    return new_schema, new_names


def _cast_to_target(table: pa.Table, target: pa.Schema) -> pa.Table:
    """Best-effort cast of ``table`` to ``target`` schema.

    Missing columns are filled with nulls; extra columns are dropped at
    this layer (caller decides whether to evolve the schema first).
    """
    first_index_by_name: dict[str, int] = {}
    for idx, name in enumerate(table.column_names):
        first_index_by_name.setdefault(name, idx)

    arrays: list[pa.Array] = []
    for f in target:
        if f.name in first_index_by_name:
            col = table.column(first_index_by_name[f.name])
            try:
                arrays.append(col.cast(f.type, safe=False))
            except Exception:  # noqa: BLE001
                arrays.append(col.cast(pa.string(), safe=False))
        else:
            arrays.append(pa.nulls(table.num_rows, type=f.type))
    return pa.Table.from_arrays(arrays, schema=target)


@dataclass
class MaterializeResult:
    iceberg_identifier: str
    table_name: str
    rows_written: int = 0
    files_consumed: int = 0
    files_skipped: int = 0
    truncated: bool = False
    schema_fields: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    sample_columns: list[str] = field(default_factory=list)


def _member_id_for_filter(m: Any) -> str:
    """Match :func:`aqp.data.pipelines.director._member_id` for filter matching."""
    archive = getattr(m, "archive_path", None)
    path = getattr(m, "path", "")
    if archive:
        return f"{path}!{archive}"
    return path


def _members_from_dataset(
    dataset: DiscoveredDataset,
    *,
    member_filter: set[str] | None = None,
) -> list[MemberRef]:
    refs: list[MemberRef] = []
    for m in dataset.members:
        if m.format == "other":
            continue
        if member_filter is not None and _member_id_for_filter(m) not in member_filter:
            continue
        refs.append(
            MemberRef(
                path=m.path,
                archive_path=m.archive_path,
                format=m.format,
                delimiter=m.delimiter,
            )
        )
    return refs


def materialize_dataset(
    dataset: DiscoveredDataset,
    *,
    namespace: str,
    table_prefix: str | None = None,
    max_rows_per_dataset: int | None = None,
    max_files_per_dataset: int | None = None,
    chunk_rows: int = 50_000,
    target_namespace: str | None = None,
    target_table: str | None = None,
    member_filter: set[str] | None = None,
) -> MaterializeResult:
    """Materialize one logical dataset into an Iceberg table.

    ``target_namespace`` / ``target_table`` override the heuristic
    derivation (used by the Director-driven pipeline). ``member_filter``
    restricts ingestion to members whose ``"<host_path>!<archive_path>"``
    id (matching :func:`aqp.data.pipelines.director._member_id`) is in
    the supplied set; ``None`` keeps every member.
    """
    effective_namespace = (target_namespace or namespace).strip() or namespace
    if target_table:
        table_name = _snake(target_table)
    else:
        table_name = _snake(
            f"{table_prefix}_{dataset.family}" if table_prefix else dataset.family
        )
    identifier = f"{effective_namespace}.{table_name}"
    result = MaterializeResult(iceberg_identifier=identifier, table_name=table_name)

    members = _members_from_dataset(dataset, member_filter=member_filter)
    if not members:
        result.error = "no tabular members"
        return result

    cap_rows = int(max_rows_per_dataset or settings.iceberg_max_rows_per_dataset or 0)
    cap_files = int(max_files_per_dataset or settings.iceberg_max_files_per_dataset or 0)

    iceberg_catalog.ensure_namespace(effective_namespace)
    # Drop+recreate so a re-ingest is idempotent at the table level.
    iceberg_catalog.drop_table(identifier)

    target_schema: pa.Schema | None = None
    rows_written = 0
    files_consumed = 0
    files_skipped = 0
    truncated = False

    for member in members:
        if cap_files and files_consumed >= cap_files:
            files_skipped += 1
            truncated = True
            continue
        try:
            consumed_any = False
            for chunk in iter_member_chunks(member, chunk_rows=chunk_rows):
                if chunk.num_rows == 0:
                    continue
                norm_schema, new_names = _normalize_schema(chunk.schema)
                chunk = chunk.rename_columns(new_names)

                if target_schema is None:
                    target_schema = norm_schema
                chunk = _cast_to_target(chunk, target_schema)

                if cap_rows and (rows_written + chunk.num_rows) > cap_rows:
                    keep = max(0, cap_rows - rows_written)
                    if keep == 0:
                        truncated = True
                        break
                    chunk = chunk.slice(0, keep)
                    truncated = True

                iceberg_catalog.append_arrow(identifier, chunk)
                rows_written += chunk.num_rows
                consumed_any = True

                if cap_rows and rows_written >= cap_rows:
                    truncated = True
                    break
            if consumed_any:
                files_consumed += 1
            else:
                files_skipped += 1
            if truncated and rows_written >= (cap_rows or 0) > 0:
                break
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "materialize: error consuming %s — %s", member.display_name, exc, exc_info=True
            )
            files_skipped += 1
            continue

    result.rows_written = rows_written
    result.files_consumed = files_consumed
    result.files_skipped = files_skipped
    result.truncated = truncated

    metadata = iceberg_catalog.table_metadata(identifier)
    result.schema_fields = list(metadata.get("fields", []))
    result.sample_columns = [f["name"] for f in result.schema_fields[:32]]
    return result
