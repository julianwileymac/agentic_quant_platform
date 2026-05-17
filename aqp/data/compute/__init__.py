"""Compute backends for the unified data engine.

Three pluggable backends:

- :class:`LocalBackend` — pure PyArrow + pandas; default for laptops
  and unit tests.
- :class:`DaskBackend` — Dask Distributed; lazy import so a missing
  ``dask[distributed]`` install doesn't break the engine.
- :class:`RayBackend` — Ray Data; lazy import as well.

:func:`pick_backend` performs auto-promotion between them based on a
size hint and the current settings.
"""
from __future__ import annotations

from aqp.data.compute.backend import ComputeBackend, ComputeBackendUnavailableError
from aqp.data.compute.local import LocalBackend
from aqp.data.compute.selection import pick_backend, size_hint_from_arrow

# Re-export Dask and Ray backends only via lazy attribute access. Importing
# them at module load would force-import ``dask`` / ``ray`` which are heavy
# optional deps. Use ``from aqp.data.compute import DaskBackend`` to grab
# them on demand.


def __getattr__(name: str):  # noqa: D401 - module-level dunder
    if name == "DaskBackend":
        from aqp.data.compute.dask import DaskBackend

        return DaskBackend
    if name == "RayBackend":
        from aqp.data.compute.ray import RayBackend

        return RayBackend
    raise AttributeError(f"module 'aqp.data.compute' has no attribute {name!r}")


__all__ = [
    "ComputeBackend",
    "ComputeBackendUnavailableError",
    "DaskBackend",
    "LocalBackend",
    "RayBackend",
    "pick_backend",
    "size_hint_from_arrow",
]
