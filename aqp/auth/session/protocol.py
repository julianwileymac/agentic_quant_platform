"""Session / transaction store contracts.

Ported (and trimmed) from
``inspiration/auth0-server-python-main/src/auth0_server_python/store/abstract.py``
(MIT, Copyright Auth0, Inc.).

The upstream ``AbstractDataStore`` carried encrypt/decrypt helpers on
the ABC; we keep that pattern so subclasses can opt-in to encrypting
payloads at rest just by setting ``encrypt_at_rest=True`` and providing
``store_secret``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TokenSet:
    """A single OAuth/OIDC token set, scoped by audience."""

    audience: str
    access_token: str
    scope: str | None = None
    expires_at: int | None = None  # Unix seconds


@dataclass
class StateData:
    """Persisted login session payload.

    Mirrors the upstream ``StateData`` shape but stays a plain
    dataclass so we don't drag pydantic into the auth boundary unless
    something else requires it.
    """

    user: dict[str, Any] = field(default_factory=dict)
    id_token: str | None = None
    refresh_token: str | None = None
    token_sets: list[TokenSet] = field(default_factory=list)
    internal: dict[str, Any] = field(default_factory=dict)


@dataclass
class TransactionData:
    """Short-lived state captured between ``login`` and ``callback``."""

    code_verifier: str
    state: str
    redirect_uri: str
    audience: str | None = None
    scope: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class _DataStoreBase(ABC):
    """Shared base — :meth:`set` / :meth:`get` / :meth:`delete`."""

    encrypt_at_rest: bool = False
    store_secret: str = ""

    @abstractmethod
    def set(self, identifier: str, payload: dict[str, Any], **options: Any) -> None: ...

    @abstractmethod
    def get(self, identifier: str, **options: Any) -> dict[str, Any] | None: ...

    @abstractmethod
    def delete(self, identifier: str, **options: Any) -> None: ...


class StateStore(_DataStoreBase):
    """Long-lived per-user session payload (login result)."""

    def delete_by_logout_token(
        self, logout_token: dict[str, Any], **options: Any
    ) -> None:
        """Optional: support OIDC back-channel logout. Default is no-op."""
        return None


class TransactionStore(_DataStoreBase):
    """Short-lived per-request login transaction payload."""


__all__ = [
    "StateData",
    "StateStore",
    "TokenSet",
    "TransactionData",
    "TransactionStore",
]
