"""Dagster Pipes wrappers — local-to-cloud bridge."""
from __future__ import annotations

from aqp_kernels.pipes.local_to_cloud import (
    cloud_run_with_pipes,
    local_pipes_context,
)

__all__ = ["cloud_run_with_pipes", "local_pipes_context"]
