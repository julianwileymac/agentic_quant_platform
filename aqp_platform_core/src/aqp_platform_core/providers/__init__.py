"""``InfrastructureProvider`` ABC + lightweight registry.

This is the core abstraction the ``aqp_control_plane`` micro-project
implements five times (docker_compose, kubernetes, aws, azure, gcp).
The ABC lives here so the contract is defined in one place and both
``aqp/`` (when it proxies a workload op back through CP) and the
control plane agree on the method signatures.

AGENTS hard rule 45 — all runtime workload operations go through
this abstraction; TerraformRuntime handles provisioning only.
"""
from __future__ import annotations

from aqp_platform_core.providers.protocol import (
    InfrastructureProvider,
    InfrastructureProviderError,
    InfrastructureProviderMeta,
    InfrastructureProviderUnavailable,
    ProviderKind,
)
from aqp_platform_core.providers.registry import (
    ProviderRegistry,
    get_provider_registry,
    register_provider_class,
)

__all__ = [
    "InfrastructureProvider",
    "InfrastructureProviderError",
    "InfrastructureProviderMeta",
    "InfrastructureProviderUnavailable",
    "ProviderKind",
    "ProviderRegistry",
    "get_provider_registry",
    "register_provider_class",
]
