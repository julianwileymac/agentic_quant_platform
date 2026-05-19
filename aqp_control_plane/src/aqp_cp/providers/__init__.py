"""Five concrete :class:`InfrastructureProvider` implementations.

Each module self-registers via :func:`register_provider_class` from
:mod:`aqp_platform_core.providers.registry` at import time. The
:func:`aqp_cp.providers.bootstrap` function imports them all to
ensure the registry is fully populated before the FastAPI app
processes its first request.
"""
from __future__ import annotations

import logging

from aqp_platform_core.providers import (
    InfrastructureProvider,
    InfrastructureProviderError,
    InfrastructureProviderUnavailable,
    ProviderKind,
    ProviderRegistry,
    get_provider_registry,
    register_provider_class,
)

logger = logging.getLogger("aqp_cp.providers")


def bootstrap() -> ProviderRegistry:
    """Import every provider module to fire its self-registration.

    Returns the populated singleton registry. Safe to call multiple
    times — duplicate registrations are silently ignored (the registry
    raises only on a NEW conflicting class, not on re-import).
    """
    for module_name in (
        "aqp_cp.providers.docker_compose",
        "aqp_cp.providers.kubernetes",
        "aqp_cp.providers.aws",
        "aqp_cp.providers.azure",
        "aqp_cp.providers.gcp",
        "aqp_cp.providers.cloudflare",
    ):
        try:
            __import__(module_name)
        except Exception:  # noqa: BLE001
            # Heavy-dep imports (boto3 / azure-mgmt / google-cloud) may
            # be absent in the slim runtime image — log + carry on.
            logger.warning(
                "provider module %s failed to load; that provider will be unavailable",
                module_name,
                exc_info=True,
            )
    return get_provider_registry()


__all__ = [
    "InfrastructureProvider",
    "InfrastructureProviderError",
    "InfrastructureProviderUnavailable",
    "ProviderKind",
    "ProviderRegistry",
    "bootstrap",
    "get_provider_registry",
    "register_provider_class",
]
