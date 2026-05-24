"""Hybrid local-to-cloud kernel + Dagster Pipes layer.

Public surface:

- :mod:`aqp_kernels.sdk_proxy` — kernel-startup hook that sets
  ``HTTPS_PROXY`` and monkey-patches ``requests.Session`` +
  ``httpx.Client`` so every vendor API call routes through the
  AQP rate-limit forward proxy.
- :mod:`aqp_kernels.cli.kernel_cmd` — ``aqp kernel`` Typer
  subcommands (start / list / attach / stop) wired into the
  monolith's CLI.
- :mod:`aqp_kernels.pipes.local_to_cloud` — Dagster Pipes
  wrappers that let a local Python script target cloud
  execution via :class:`dagster_pipes.PipesK8sClient`.
"""
from __future__ import annotations

from aqp_kernels.sdk_proxy import (
    install_kernel_runtime,
    is_kernel_runtime,
)

__all__ = [
    "install_kernel_runtime",
    "is_kernel_runtime",
]
