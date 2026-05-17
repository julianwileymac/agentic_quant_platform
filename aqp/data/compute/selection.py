"""Auto-promote between local / Dask / Ray based on a size hint."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from aqp.data.engine.manifest import ComputeBackendKind, ComputeSpec

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@dataclass(frozen=True)
class SizeHint:
    """Coarse size estimate handed to :func:`pick_backend`."""

    rows: int = 0
    bytes: int = 0
    partitions: int = 1


def size_hint_from_arrow(table: pa.Table | None) -> SizeHint:
    """Build a :class:`SizeHint` from a pyarrow table."""
    if table is None:
        return SizeHint()
    try:
        rows = int(table.num_rows)
        nbytes = int(table.nbytes)
    except Exception:  # noqa: BLE001
        return SizeHint()
    return SizeHint(rows=rows, bytes=nbytes)


def _pick_kind(
    hint: SizeHint,
    *,
    requested: ComputeBackendKind,
    local_to_dask_rows: int,
    local_to_ray_rows: int,
    local_to_dask_bytes: int,
    local_to_ray_bytes: int,
) -> ComputeBackendKind:
    if requested != ComputeBackendKind.AUTO:
        return requested

    rows = max(int(hint.rows or 0), 0)
    nbytes = max(int(hint.bytes or 0), 0)
    if local_to_ray_rows and rows >= local_to_ray_rows:
        return ComputeBackendKind.RAY
    if local_to_ray_bytes and nbytes >= local_to_ray_bytes:
        return ComputeBackendKind.RAY
    if local_to_dask_rows and rows >= local_to_dask_rows:
        return ComputeBackendKind.DASK
    if local_to_dask_bytes and nbytes >= local_to_dask_bytes:
        return ComputeBackendKind.DASK
    return ComputeBackendKind.LOCAL


def pick_backend(
    hint: SizeHint | None = None,
    *,
    requested: ComputeBackendKind | str = ComputeBackendKind.AUTO,
    spec: ComputeSpec | None = None,
    overrides: dict[str, Any] | None = None,
) -> ComputeSpec:
    """Return a :class:`ComputeSpec` with a concrete backend choice.

    ``hint`` is the row/byte estimate. ``requested`` is the user
    preference (``auto`` lets the function decide based on settings
    thresholds). ``spec`` is the manifest-supplied spec we should clone
    rather than rebuild from scratch.

    Thresholds come from :class:`aqp.config.Settings` if present;
    overrides can be passed for tests via ``overrides=...``.
    """
    from aqp.config import settings

    hint = hint or SizeHint()
    if isinstance(requested, str):
        try:
            requested = ComputeBackendKind(requested)
        except ValueError:
            requested = ComputeBackendKind.AUTO

    base = spec.model_copy() if spec else ComputeSpec()
    if requested != ComputeBackendKind.AUTO:
        base.backend = requested

    overrides = overrides or {}

    local_to_dask_rows = int(
        overrides.get(
            "compute_local_to_dask_rows",
            getattr(settings, "compute_local_to_dask_rows", 1_000_000),
        )
    )
    local_to_ray_rows = int(
        overrides.get(
            "compute_local_to_ray_rows",
            getattr(settings, "compute_local_to_ray_rows", 25_000_000),
        )
    )
    local_to_dask_bytes = int(
        overrides.get(
            "compute_local_to_dask_bytes",
            getattr(settings, "compute_local_to_dask_bytes", 256 * 1024 * 1024),
        )
    )
    local_to_ray_bytes = int(
        overrides.get(
            "compute_local_to_ray_bytes",
            getattr(settings, "compute_local_to_ray_bytes", 8 * 1024 * 1024 * 1024),
        )
    )

    chosen = _pick_kind(
        hint,
        requested=base.backend,
        local_to_dask_rows=local_to_dask_rows,
        local_to_ray_rows=local_to_ray_rows,
        local_to_dask_bytes=local_to_dask_bytes,
        local_to_ray_bytes=local_to_ray_bytes,
    )
    base.backend = chosen
    if chosen == ComputeBackendKind.DASK and not base.dask_address:
        base.dask_address = getattr(settings, "dask_scheduler_address", "") or None
    if chosen == ComputeBackendKind.RAY and not base.ray_address:
        base.ray_address = getattr(settings, "ray_address", "") or None
    return base


__all__ = ["SizeHint", "pick_backend", "size_hint_from_arrow"]
