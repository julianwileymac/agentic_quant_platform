"""Content addressing for lineage dataset vertices (Workstream A).

The plan's invariant: every ``DatasetVertex`` row carries a
``content_hash`` (SHA-256) that uniquely identifies a snapshot of a
dataset. For Iceberg-backed datasets, the snapshot manifest list IS
the natural content address — we surface a stable digest over
``(manifest_list_location || snapshot_id)`` so the vertex table has a
uniform shape regardless of backend.

This module is intentionally side-effect-free and import-light: callers
that hit Iceberg snapshot metadata go through
:func:`iceberg_snapshot_address`, callers that have only a URI fall
back to :func:`fallback_content_hash`. Both return a 64-char hex digest
suitable for the ``DatasetVertex.content_hash`` column.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


class IcebergSnapshotAddress(NamedTuple):
    """Tuple persisted on a :class:`DatasetVertex` for Iceberg datasets."""

    content_hash: str
    snapshot_id: int | None
    manifest_list_location: str | None


def iceberg_snapshot_address(table_identifier: str | None) -> IcebergSnapshotAddress:
    """Compute the content address for the current snapshot of ``table_identifier``.

    Returns ``(content_hash, snapshot_id, manifest_list_location)``.
    All three fields fall back to ``None`` / empty hash when the table
    is missing or the catalog is unreachable; the writer treats those
    as "best-effort" rows that still produce a useful graph edge.

    The hash is intentionally over ``(manifest_list || snapshot_id)``
    because:

    - Two re-ingestions that produce the same bytes share the same
      manifest list location and snapshot id at the PyIceberg layer,
      so the hash collides naturally — the graph deduplicates.
    - We avoid reading the underlying Parquet bytes; with a 100 GB
      Iceberg table that would be intolerable. Iceberg's own content
      address is by design the manifest reference.
    """
    if not table_identifier:
        return IcebergSnapshotAddress("", None, None)
    try:
        from aqp.data.iceberg_catalog import load_table  # local import to avoid cycle

        table = load_table(table_identifier)
    except Exception:  # noqa: BLE001
        return IcebergSnapshotAddress("", None, None)
    if table is None:
        return IcebergSnapshotAddress("", None, None)
    try:
        snap = table.current_snapshot()
    except Exception:  # noqa: BLE001
        return IcebergSnapshotAddress("", None, None)
    if snap is None:
        return IcebergSnapshotAddress("", None, None)
    snapshot_id = int(getattr(snap, "snapshot_id", 0) or 0) or None
    manifest_list = str(getattr(snap, "manifest_list", "") or "").strip() or None

    parts: list[str] = [str(table_identifier)]
    if manifest_list:
        parts.append(manifest_list)
    if snapshot_id is not None:
        parts.append(str(snapshot_id))
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return IcebergSnapshotAddress(digest, snapshot_id, manifest_list)


def fallback_content_hash(*parts: Any) -> str:
    """Best-effort SHA-256 over the provided parts.

    Used for non-Iceberg datasets (Parquet directories, external APIs,
    Redis snapshots). Caller decides which strings uniquely identify
    the snapshot — typical inputs are the table identifier plus a
    monotonic counter or a content checksum the source already
    provides.
    """
    payload = "\x1f".join(str(part) for part in parts if part is not None)
    if not payload:
        return ""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "IcebergSnapshotAddress",
    "fallback_content_hash",
    "iceberg_snapshot_address",
]
