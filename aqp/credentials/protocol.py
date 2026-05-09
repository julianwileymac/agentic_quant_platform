"""Credential protocol — keys, values, and the registered store ABC.

The protocol is deliberately small: a :class:`SecretStore` resolves
:class:`CredentialKey` to a :class:`Credential` (plain dict of string
fields) or returns ``None`` when it has no value to offer. The
:class:`CredentialResolver` walks an ordered list of stores until one
returns a hit.

Concrete stores (under :mod:`aqp.credentials.stores`) subclass
:class:`SecretStore` and set ``store_kind`` + ``store_priority``. The
:class:`SecretStoreMeta` metaclass auto-registers them in the
``"secret_store"`` bucket of :mod:`aqp.core.registry` so the API and
diagnostics tooling can introspect the active resolution chain.
"""
from __future__ import annotations

import logging
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from aqp.core.registry import register

logger = logging.getLogger(__name__)


SECRET_STORE_KIND = "secret_store"


# Priority ordering — lower numbers resolve first. M2M plugs in front of
# the bootstrap file so a configured token issuer wins over the static
# minted secret. Env is the always-available safety net.
PRIORITY_M2M = 10
PRIORITY_FILE = 50
PRIORITY_ENV = 100


class CredentialNotFoundError(KeyError):
    """Raised when no store can resolve a key and no default is supplied."""


@dataclass(frozen=True)
class CredentialKey:
    """Identifies a credential the resolver can mint or fetch.

    ``service`` is the logical service name (``"polaris"``, ``"trino"``,
    ``"minio"``). ``purpose`` qualifies the credential within the
    service (``"oauth"`` for OAuth client credentials, ``"sts"`` for
    short-lived S3 tokens, ``"basic"`` for username+password). The pair
    is the key both file stores and the M2M issuer use to address a
    specific credential.
    """

    service: str
    purpose: str = "default"

    def __str__(self) -> str:
        return f"{self.service}:{self.purpose}"


@dataclass(frozen=True)
class Credential:
    """Resolved credential payload.

    ``fields`` is a free-form ``{name: value}`` mapping consumers
    interpret per service:

    - ``polaris:oauth`` → ``{"client_id": ..., "client_secret": ...}``
    - ``polaris:rest`` → ``{"credential": "client_id:client_secret"}``
    - ``trino:basic``  → ``{"user": ..., "password": ...}``
    - ``minio:sts``    → ``{"access_key": ..., "secret_key": ..., "session_token": ...}``

    ``source`` is the store-kind label (``"file"``, ``"env"``, ``"m2m"``)
    so callers and the diagnostics endpoint can show *where* the
    runtime cred came from.

    ``ttl_seconds`` is set by the M2M store so the resolver can refresh
    short-lived tokens. ``None`` means "no expiry" (file / env stores).
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
            raise KeyError(f"Credential field {name!r} missing in {self.source} payload")
        return value

    def merge_default(self, default: dict[str, str] | None) -> Credential:
        """Return a new credential whose missing fields are filled from ``default``."""
        if not default:
            return self
        merged = {str(k): str(v) for k, v in default.items() if v is not None and v != ""}
        merged.update({k: v for k, v in self.fields.items() if v is not None and v != ""})
        return Credential(fields=merged, source=self.source, ttl_seconds=self.ttl_seconds)


class SecretStoreMeta(ABCMeta):
    """Metaclass that auto-registers concrete :class:`SecretStore` subclasses.

    Mirrors :class:`aqp.rl.core.base.RLComponentMeta`:

    1. Skip abstract bases (``__abstract_secret_store__ = True`` or names
       starting with ``Base`` / ``_``).
    2. Validate ``store_kind`` is a non-empty string.
    3. Call :func:`aqp.core.registry.register` so
       ``list_by_kind("secret_store")`` enumerates every concrete store.
    """

    def __new__(mcs, name, bases, namespace, **kwargs):  # type: ignore[override]
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if namespace.get("__abstract_secret_store__", False):
            return cls
        if name.startswith(("Base", "_")):
            return cls
        store_kind = getattr(cls, "store_kind", None)
        if not store_kind:
            return cls
        alias = getattr(cls, "store_alias", None) or cls.__name__
        try:
            register(name=alias, kind=SECRET_STORE_KIND)(cls)
        except Exception:  # noqa: BLE001 - never fail import on a registry hiccup
            logger.debug("SecretStore auto-registration failed for %s", name, exc_info=True)
        return cls


class SecretStore(metaclass=SecretStoreMeta):
    """Abstract base for credential providers.

    Subclasses set:

    - ``store_kind``: short label included in :class:`Credential.source`
      (e.g. ``"file"``, ``"env"``, ``"m2m"``).
    - ``store_priority``: integer; lower wins. Use the
      :data:`PRIORITY_*` constants where possible.
    - ``store_alias`` (optional): registry alias, defaults to the class
      name.

    :meth:`get` returns ``None`` when this store has no opinion on the
    key — the resolver moves to the next store. Raise
    :class:`CredentialNotFoundError` only when the store explicitly
    *blocks* fallback.
    """

    __abstract_secret_store__: ClassVar[bool] = True

    store_kind: ClassVar[str] = ""
    store_alias: ClassVar[str | None] = None
    store_priority: ClassVar[int] = PRIORITY_ENV

    @abstractmethod
    def get(self, key: CredentialKey) -> Credential | None:
        """Return a :class:`Credential` for ``key`` or ``None`` to defer."""

    def describe(self) -> dict[str, Any]:
        """JSON-friendly summary for the diagnostics endpoint."""
        return {
            "alias": self.store_alias or self.__class__.__name__,
            "kind": self.store_kind,
            "priority": int(self.store_priority),
        }


__all__ = [
    "PRIORITY_ENV",
    "PRIORITY_FILE",
    "PRIORITY_M2M",
    "SECRET_STORE_KIND",
    "Credential",
    "CredentialKey",
    "CredentialNotFoundError",
    "SecretStore",
    "SecretStoreMeta",
]
