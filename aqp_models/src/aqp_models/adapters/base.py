"""RegistryAdapter ABC + metaclass-driven registration.

Mirrors the RL :class:`RLComponent` metaclass pattern: every concrete
:class:`RegistryAdapter` subclass auto-registers under its
``adapter_kind`` so adding a new external registry (TorchHub, an
internal artefact store, a private cookiecutter index) is a single
class definition.
"""
from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from aqp.core.registry import register

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PullResult:
    """Outcome of a :meth:`RegistryAdapter.pull` call."""

    ok: bool
    adapter_kind: str
    model_name: str
    revision: str | None
    local_path: Path | None
    sha256: str | None = None
    size_bytes: int = 0
    examples_loaded: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    elapsed_ms: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "adapter_kind": self.adapter_kind,
            "model_name": self.model_name,
            "revision": self.revision,
            "local_path": str(self.local_path) if self.local_path else None,
            "sha256": self.sha256,
            "size_bytes": int(self.size_bytes),
            "examples_loaded": int(self.examples_loaded),
            "metadata": dict(self.metadata),
            "warnings": list(self.warnings),
            "error": self.error,
            "elapsed_ms": float(self.elapsed_ms),
        }


_ADAPTER_REGISTRY: dict[str, type["RegistryAdapter"]] = {}
_REGISTRY_LOCK = threading.RLock()


class RegistryAdapterMeta(type(ABC)):
    """Metaclass that auto-registers concrete adapters by ``adapter_kind``."""

    def __init__(
        cls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        super().__init__(name, bases, namespace, **kwargs)
        kind = namespace.get("adapter_kind") or getattr(cls, "adapter_kind", "")
        if kind and not _is_abstract(cls):
            with _REGISTRY_LOCK:
                _ADAPTER_REGISTRY[kind] = cls
            # Tag in the central typed registry for UI discovery.
            try:
                register(name, kind="registry_adapter", tags=(f"adapter:{kind}",))(cls)
            except Exception:  # noqa: BLE001 - central registry may not be ready in tests
                logger.debug("central registry tag failed for %s", name, exc_info=True)


def _is_abstract(cls: Any) -> bool:
    return bool(getattr(cls, "__abstractmethods__", set()))


class RegistryAdapter(ABC, metaclass=RegistryAdapterMeta):
    """Abstract adapter for external model registries."""

    adapter_kind: ClassVar[str] = ""
    default_cache_subdir: ClassVar[str] = "external_models"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @abstractmethod
    def pull(
        self,
        model_name: str,
        *,
        revision: str | None = None,
        cache_dir: str | None = None,
        include_examples: bool = False,
    ) -> PullResult:
        """Pull ``model_name`` from the external registry to a local path."""

    def import_examples(self, model_name: str, *, target_dir: str | None = None) -> int:
        """Best-effort: download the example notebook / config files.

        Subclasses override when the upstream registry exposes a
        consistent ``examples/`` surface. Default implementation does
        nothing and returns 0.
        """
        del model_name, target_dir
        return 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def resolve_token(self, *, purpose: str = "api_token") -> str | None:
        """Resolve the adapter's auth token via the credential chain.

        Subclasses set ``adapter_kind`` (e.g. ``"huggingface"``) which
        maps onto ``CredentialKey(service=adapter_kind, purpose=purpose)``.
        Returns ``None`` when no store offers a value.
        """
        try:
            from aqp.credentials.protocol import CredentialKey
            from aqp.credentials.resolver import get_resolver

            cred = get_resolver().resolve(
                CredentialKey(service=self.adapter_kind, purpose=purpose),
            )
            token = (cred.fields.get("token") or cred.fields.get("api_token") or "").strip()
            return token or None
        except Exception:  # noqa: BLE001
            logger.debug("credential resolution failed for %s", self.adapter_kind, exc_info=True)
            return None

    def cache_dir_for(self, cache_dir: str | None) -> Path:
        if cache_dir:
            target = Path(cache_dir)
        else:
            try:
                from aqp.config import settings

                base = Path(getattr(settings, "data_dir", "data"))
            except Exception:  # noqa: BLE001
                base = Path("data")
            target = base / self.default_cache_subdir / self.adapter_kind
        target.mkdir(parents=True, exist_ok=True)
        return target


def get_adapter(adapter_kind: str) -> RegistryAdapter:
    """Resolve an adapter by ``adapter_kind`` (e.g. ``"huggingface"``)."""
    cls = _ADAPTER_REGISTRY.get(adapter_kind)
    if cls is None:
        raise KeyError(
            f"unknown registry adapter {adapter_kind!r}; known: {sorted(_ADAPTER_REGISTRY)}"
        )
    return cls()


def list_adapters() -> list[dict[str, Any]]:
    return [
        {"adapter_kind": kind, "class": cls.__name__}
        for kind, cls in sorted(_ADAPTER_REGISTRY.items())
    ]


__all__ = [
    "PullResult",
    "RegistryAdapter",
    "RegistryAdapterMeta",
    "get_adapter",
    "list_adapters",
]
