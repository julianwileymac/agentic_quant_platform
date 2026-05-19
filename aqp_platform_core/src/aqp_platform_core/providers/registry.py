"""Lightweight registry for :class:`InfrastructureProvider` implementations.

The control plane wires its five providers in at startup. Tests use
:func:`reset_provider_registry` to start clean. Mirrors the spirit of
``aqp.core.registry`` but without the legacy "kind bucket" surface —
providers are a single, flat namespace keyed by alias.
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from aqp_platform_core.providers.protocol import (
    InfrastructureProvider,
    InfrastructureProviderError,
    ProviderKind,
)

if TYPE_CHECKING:
    pass


class ProviderRegistry:
    """In-process registry of provider classes + active instances.

    Thread-safe. Holds class objects (resolved when an instance is
    requested via :meth:`get_or_create`) so the control plane can
    register lazily even before its credentials are available.
    """

    def __init__(self) -> None:
        self._classes: dict[str, type[InfrastructureProvider]] = {}
        self._instances: dict[str, InfrastructureProvider] = {}
        self._lock = threading.RLock()

    def register(
        self,
        alias: str,
        cls: type[InfrastructureProvider],
        *,
        replace: bool = False,
    ) -> None:
        """Register ``cls`` under ``alias``.

        Raises :class:`InfrastructureProviderError` if ``alias`` is
        already registered and ``replace=False``.
        """
        with self._lock:
            if alias in self._classes and not replace:
                raise InfrastructureProviderError(
                    f"Provider alias {alias!r} already registered",
                    code="duplicate_provider",
                )
            self._classes[alias] = cls
            # Drop any cached instance so the next get_or_create uses
            # the new class.
            self._instances.pop(alias, None)

    def get_class(self, alias: str) -> type[InfrastructureProvider]:
        with self._lock:
            try:
                return self._classes[alias]
            except KeyError as exc:
                raise InfrastructureProviderError(
                    f"No provider registered under alias {alias!r}",
                    code="unknown_provider",
                ) from exc

    def get_or_create(
        self,
        alias: str,
        *,
        factory_kwargs: dict[str, object] | None = None,
    ) -> InfrastructureProvider:
        """Return the active instance for ``alias``, creating it on first call."""
        with self._lock:
            if alias in self._instances:
                return self._instances[alias]
            cls = self.get_class(alias)
            instance = cls(**(factory_kwargs or {}))  # type: ignore[arg-type]
            self._instances[alias] = instance
            return instance

    def replace_instance(
        self, alias: str, instance: InfrastructureProvider
    ) -> None:
        """Inject ``instance`` for ``alias`` (used by tests + dynamic config)."""
        with self._lock:
            self._instances[alias] = instance
            self._classes[alias] = type(instance)

    def aliases(self) -> list[str]:
        with self._lock:
            return sorted(self._classes)

    def aliases_by_kind(self, kind: ProviderKind) -> list[str]:
        with self._lock:
            return sorted(
                alias
                for alias, cls in self._classes.items()
                if getattr(cls, "provider_kind", None) == kind
            )

    def clear(self) -> None:
        """Drop every registered provider — test helper only."""
        with self._lock:
            self._classes.clear()
            self._instances.clear()


_REGISTRY: ProviderRegistry | None = None
_LOCK = threading.Lock()


def get_provider_registry() -> ProviderRegistry:
    """Return the process-wide provider registry singleton."""
    global _REGISTRY
    if _REGISTRY is None:
        with _LOCK:
            if _REGISTRY is None:
                _REGISTRY = ProviderRegistry()
    return _REGISTRY


def register_provider_class(
    alias: str,
    cls: type[InfrastructureProvider] | None = None,
    *,
    replace: bool = False,
):
    """Register a provider class. Works as a function OR a decorator.

    Function form::

        register_provider_class("docker_compose", DockerComposeProvider)

    Decorator form (with args)::

        @register_provider_class("docker_compose")
        class DockerComposeProvider(InfrastructureProvider):
            ...

    Decorator form (with replace flag)::

        @register_provider_class("docker_compose", replace=True)
        class DockerComposeProvider(InfrastructureProvider):
            ...
    """
    if cls is not None:
        get_provider_registry().register(alias, cls, replace=replace)
        return cls

    def _decorator(target: type[InfrastructureProvider]) -> type[InfrastructureProvider]:
        get_provider_registry().register(alias, target, replace=replace)
        return target

    return _decorator


__all__ = [
    "ProviderRegistry",
    "get_provider_registry",
    "register_provider_class",
]
