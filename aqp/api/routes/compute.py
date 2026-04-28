"""Compute backend status + selection helpers."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from aqp.config import settings
from aqp.data.compute import LocalBackend
from aqp.data.compute.selection import SizeHint, pick_backend
from aqp.data.engine.manifest import ComputeBackendKind, ComputeSpec

router = APIRouter(prefix="/compute", tags=["compute"])


class PickRequest(BaseModel):
    rows: int = 0
    bytes: int = 0
    requested: str = "auto"


@router.get("/status")
def status() -> dict[str, Any]:
    """Report backend availability + cluster knobs."""
    dask_ok = True
    ray_ok = True
    try:
        import dask  # noqa: F401
    except Exception:
        dask_ok = False
    try:
        import ray  # noqa: F401
    except Exception:
        ray_ok = False

    return {
        "default_backend": settings.compute_backend_default,
        "thresholds": {
            "local_to_dask_rows": settings.compute_local_to_dask_rows,
            "local_to_ray_rows": settings.compute_local_to_ray_rows,
            "local_to_dask_bytes": settings.compute_local_to_dask_bytes,
            "local_to_ray_bytes": settings.compute_local_to_ray_bytes,
        },
        "dask": {
            "available": dask_ok,
            "scheduler_address": settings.dask_scheduler_address or None,
            "n_workers": settings.dask_n_workers,
            "threads_per_worker": settings.dask_threads_per_worker,
        },
        "ray": {
            "available": ray_ok,
            "address": settings.ray_address or None,
            "init_kwargs": settings.ray_init_kwargs,
        },
        "engine": {
            "default_chunk_rows": settings.engine_default_chunk_rows,
            "max_concurrent_pipelines": settings.engine_max_concurrent_pipelines,
        },
    }


@router.post("/pick")
def pick_compute(payload: PickRequest) -> dict[str, Any]:
    """Auto-select a compute backend for a ``(rows, bytes)`` hint."""
    spec = pick_backend(
        SizeHint(rows=int(payload.rows), bytes=int(payload.bytes)),
        requested=ComputeBackendKind(payload.requested),
        spec=ComputeSpec(),
    )
    return spec.model_dump(mode="json")


@router.get("/local")
def describe_local() -> dict[str, Any]:
    backend = LocalBackend()
    return backend.describe()
