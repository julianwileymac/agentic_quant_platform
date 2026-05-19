"""Provider registry — register / lookup / instance caching."""
from __future__ import annotations

import pytest

from aqp_platform_core.models.config import ConfigMapPatch, ServiceConfig
from aqp_platform_core.models.deployment import (
    DeploymentSpec,
    DeploymentStatus,
)
from aqp_platform_core.models.health import HealthStatus, ProviderHealth
from aqp_platform_core.providers import (
    InfrastructureProvider,
    InfrastructureProviderError,
    ProviderKind,
    ProviderRegistry,
)


class _StubProvider(InfrastructureProvider):
    provider_kind = ProviderKind.DOCKER_COMPOSE
    provider_alias = "stub"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def health(self) -> ProviderHealth:
        self.calls.append("health")
        return ProviderHealth(
            provider="stub",
            status=HealthStatus.OK,
            available=True,
        )

    async def start(self, spec: DeploymentSpec) -> DeploymentStatus:
        self.calls.append(f"start:{spec.service_id}")
        return DeploymentStatus(service_id=spec.service_id, provider="stub")

    async def stop(self, service_id: str, *, namespace=None) -> DeploymentStatus:
        return DeploymentStatus(service_id=service_id, provider="stub")

    async def scale(
        self, service_id: str, replicas: int, *, namespace=None
    ) -> DeploymentStatus:
        return DeploymentStatus(
            service_id=service_id, provider="stub", replicas_desired=replicas
        )

    async def status(self, service_id: str, *, namespace=None) -> DeploymentStatus:
        return DeploymentStatus(service_id=service_id, provider="stub")

    async def list_deployments(self, *, namespace=None) -> list[DeploymentStatus]:
        return []


def test_register_and_get_class() -> None:
    registry = ProviderRegistry()
    registry.register("stub", _StubProvider)
    assert registry.get_class("stub") is _StubProvider


def test_duplicate_alias_rejected_without_replace() -> None:
    registry = ProviderRegistry()
    registry.register("stub", _StubProvider)
    with pytest.raises(InfrastructureProviderError, match="already registered"):
        registry.register("stub", _StubProvider)


def test_replace_allowed_with_flag() -> None:
    registry = ProviderRegistry()
    registry.register("stub", _StubProvider)
    registry.register("stub", _StubProvider, replace=True)
    assert registry.get_class("stub") is _StubProvider


def test_get_or_create_caches_instance() -> None:
    registry = ProviderRegistry()
    registry.register("stub", _StubProvider)
    a = registry.get_or_create("stub")
    b = registry.get_or_create("stub")
    assert a is b


def test_aliases_by_kind_filters() -> None:
    registry = ProviderRegistry()
    registry.register("stub", _StubProvider)

    class _OtherKind(_StubProvider):
        provider_kind = ProviderKind.KUBERNETES
        provider_alias = "k8s"

    registry.register("k8s", _OtherKind)

    assert registry.aliases_by_kind(ProviderKind.DOCKER_COMPOSE) == ["stub"]
    assert registry.aliases_by_kind(ProviderKind.KUBERNETES) == ["k8s"]


def test_unknown_alias_raises() -> None:
    registry = ProviderRegistry()
    with pytest.raises(InfrastructureProviderError, match="No provider"):
        registry.get_class("missing")


def test_clear_resets_registry() -> None:
    registry = ProviderRegistry()
    registry.register("stub", _StubProvider)
    registry.clear()
    assert registry.aliases() == []
