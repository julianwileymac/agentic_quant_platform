"""AQP Dagster code location.

This package is the gRPC entrypoint loaded by the cluster's Dagster
instance. Importing :mod:`aqp.dagster.definitions` returns a single
:class:`dagster.Definitions` aggregating every asset, job, schedule,
sensor and resource AQP exposes.

Run locally with::

    dagster api grpc -m aqp.dagster.definitions

The cluster picks this up via ``values-pipelines-user-code.yaml`` in
the rpi_kubernetes repo (separate PR; see ``docs/dagster.md``).
"""

from __future__ import annotations

# Re-export ``defs`` lazily so importing this module does not require
# Dagster at import time.
__all__ = ["defs"]


def __getattr__(name: str):  # noqa: D401 - module dunder
    if name == "defs":
        from aqp.dagster.definitions import defs

        return defs
    raise AttributeError(f"module 'aqp.dagster' has no attribute {name!r}")
