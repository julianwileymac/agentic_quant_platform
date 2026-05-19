"""Bootstrap test — all five providers register against the ABC."""
from __future__ import annotations

import pytest

from aqp_platform_core.providers import (
    InfrastructureProvider,
    ProviderKind,
    get_provider_registry,
)


def test_bootstrap_registers_all_five() -> None:
    """The bootstrap helper imports every provider module."""
    from aqp_cp.providers import bootstrap

    registry = bootstrap()
    aliases = registry.aliases()
    for expected in ("docker_compose", "kubernetes", "aws", "azure", "gcp"):
        assert expected in aliases, f"{expected} missing from {aliases}"


def test_every_provider_subclasses_abc() -> None:
    from aqp_cp.providers import bootstrap

    registry = bootstrap()
    for alias in registry.aliases():
        cls = registry.get_class(alias)
        assert issubclass(cls, InfrastructureProvider), f"{alias} does not subclass ABC"


def test_provider_kind_matches_alias() -> None:
    from aqp_cp.providers import bootstrap

    registry = bootstrap()
    expected_kind: dict[str, ProviderKind] = {
        "docker_compose": ProviderKind.DOCKER_COMPOSE,
        "kubernetes": ProviderKind.KUBERNETES,
        "aws": ProviderKind.AWS,
        "azure": ProviderKind.AZURE,
        "gcp": ProviderKind.GCP,
    }
    for alias, kind in expected_kind.items():
        cls = registry.get_class(alias)
        assert cls.provider_kind == kind
        assert cls.provider_alias == alias
