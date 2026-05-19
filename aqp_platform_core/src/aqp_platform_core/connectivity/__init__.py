"""Connectivity configuration — service URL resolution.

The :class:`ConnectivityConfig` model is the single source of truth
for "where does the AQP client / control plane reach backend X?".
It's read at request time (not import time) so URLs can be reloaded
without a process restart.

In docker-compose, the defaults point at compose service names
(``http://aqp-core:8000``). In Kubernetes, the env vars are
overridden to point at cluster DNS
(``http://aqp-core.default.svc.cluster.local``). When
``AQP_INGRESS_BASE_URL`` is set, all URLs are derived from it by
appending standard path prefixes — this is the hybrid / external
Ingress mode.
"""
from __future__ import annotations

from aqp_platform_core.connectivity.config import (
    ConnectivityConfig,
    ServiceRoute,
    get_connectivity_config,
    reset_connectivity_config,
)

__all__ = [
    "ConnectivityConfig",
    "ServiceRoute",
    "get_connectivity_config",
    "reset_connectivity_config",
]
