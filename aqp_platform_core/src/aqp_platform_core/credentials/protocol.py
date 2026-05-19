"""Credential resolver protocol — pure ABC + value types.

Mirrors :mod:`aqp.credentials.protocol` minus the registry-side
metaclass. Concrete stores live in:

- ``aqp/credentials/stores/`` (env / file / m2m) — auto-registered into
  ``aqp.core.registry`` via the ``aqp/`` metaclass that subclasses this
  :class:`SecretStore`.
- ``aqp_control_plane/src/aqp_cp/credentials/`` (control-plane-specific
  stores; today just env) — registered explicitly via the local
  resolver, no metaclass.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


# Priority ordering — lower numbers resolve first.
PRIORITY_M2M = 10
PRIORITY_FILE = 50
PRIORITY_ENV = 100


class CredentialNotFoundError(KeyError):
    """Raised when no store can resolve a key and no default is supplied."""


@dataclass(frozen=True, slots=True)
class CredentialKey:
    """Identifies a credential the resolver can mint or fetch.

    ``service`` is the logical service name (``"polaris"``, ``"trino"``,
    ``"minio"``). ``purpose`` qualifies the credential within the
    service (``"oauth"``, ``"sts"``, ``"basic"``).
    """

    service: str
    purpose: str = "default"

    def __str__(self) -> str:
        return f"{self.service}:{self.purpose}"


@dataclass(frozen=True, slots=True)
class Credential:
    """Resolved credential payload.

    ``fields`` is a free-form mapping consumers interpret per service.
    ``source`` is the store-kind label (``"file"``, ``"env"``,
    ``"m2m"``). ``ttl_seconds`` is set by the M2M store so the resolver
    can refresh short-lived tokens; ``None`` means "no expiry".
    """

    fields: dict[str, str] = field(default_factory=dict)
    source: str = "unknown"
    ttl_seconds: int | None = None

    def get(self, name: str, default: str | None = None) -> str | None:
        value = self.fields.get(name)
        if value is None or value == "":
            return default
        return str(value)

    def require(self, name: str) -> str:
        value = self.get(name)
        if value is None:
            raise KeyError(
                f"Credential field {name!r} missing in {self.source} payload"
            )
        return value


class SecretStore(ABC):
    """Abstract base for credential providers.

    Subclasses set:

    - ``store_kind``: short label included in :class:`Credential.source`
      (e.g. ``"file"``, ``"env"``, ``"m2m"``).
    - ``store_priority``: integer; lower wins. Use the
      :data:`PRIORITY_*` constants where possible.

    :meth:`get` returns ``None`` when this store has no opinion on the
    key — the resolver moves to the next store. Raise
    :class:`CredentialNotFoundError` only when the store explicitly
    *blocks* fallback.
    """

    store_kind: ClassVar[str] = ""
    store_priority: ClassVar[int] = PRIORITY_ENV

    @abstractmethod
    def get(self, key: CredentialKey) -> Credential | None:
        """Return a :class:`Credential` for ``key`` or ``None`` to defer."""

    def describe(self) -> dict[str, Any]:
        return {
            "class": self.__class__.__name__,
            "kind": self.store_kind,
            "priority": int(self.store_priority),
        }


__all__ = [
    "PRIORITY_ENV",
    "PRIORITY_FILE",
    "PRIORITY_M2M",
    "Credential",
    "CredentialKey",
    "CredentialNotFoundError",
    "SecretStore",
]
