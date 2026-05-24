"""External OAuth2 provider ABC + auto-registering metaclass.

Mirrors :class:`aqp.auth.providers.protocol.IdentityProviderMeta` —
subclasses set ``provider_slug`` (e.g. ``"github"``, ``"bloomberg"``)
and the metaclass calls :func:`aqp.core.registry.register` so the
frontend wizard + ``data.oauth.list_connections`` MCP tool can
enumerate them.

Distinct from :class:`IdentityProvider` because the contracts differ:

- :class:`IdentityProvider` handles AQP-tenant login (Auth0 / Entra /
  Cloudflare Access). One per deployment.
- :class:`ExternalOAuthProvider` handles "this user authorising AQP
  to call an external API on their behalf". Many per deployment;
  every connected external API is one of these.

Provider authors only need to provide three methods:

- :meth:`authorize_url(state, code_challenge, redirect_uri)` — build
  the PKCE authorize URL.
- :meth:`exchange_code(code, code_verifier, redirect_uri)` — redeem
  the auth code for tokens.
- :meth:`refresh(refresh_token)` — exchange a refresh token for a
  fresh access token.

The generic provider implements all three against any
standards-compliant OAuth2 AS; per-provider subclasses override only
what differs (e.g. Bloomberg's non-standard scope encoding).
"""
from __future__ import annotations

import logging
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from aqp.core.registry import register

logger = logging.getLogger(__name__)


EXTERNAL_OAUTH_PROVIDER_KIND = "external_oauth_provider"


class ExternalOAuthProviderError(Exception):
    pass


@dataclass(frozen=True)
class ExternalProviderConfig:
    authorize_endpoint: str
    token_endpoint: str
    client_id: str
    client_secret: str = ""
    default_scope: str = ""
    audience: str = ""
    extra_params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExternalTokenResponse:
    access_token: str
    refresh_token: str = ""
    expires_in: int | None = None
    token_type: str = "Bearer"
    scope: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class ExternalOAuthProviderMeta(ABCMeta):
    """Auto-register concrete :class:`ExternalOAuthProvider` classes."""

    def __new__(mcs, name, bases, namespace, **kwargs):  # type: ignore[override]
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if namespace.get("__abstract_provider__", False):
            return cls
        if name.startswith(("Base", "_")):
            return cls
        slug = getattr(cls, "provider_slug", None)
        if not slug:
            return cls
        alias = getattr(cls, "provider_alias", None) or cls.__name__
        try:
            register(name=alias, kind=EXTERNAL_OAUTH_PROVIDER_KIND, source=str(slug))(cls)
        except Exception:  # noqa: BLE001
            logger.debug(
                "ExternalOAuthProvider auto-registration failed for %s", name, exc_info=True
            )
        return cls


class ExternalOAuthProvider(metaclass=ExternalOAuthProviderMeta):
    """ABC for per-source external OAuth providers."""

    __abstract_provider__: ClassVar[bool] = True

    provider_slug: ClassVar[str] = ""
    provider_alias: ClassVar[str | None] = None
    display_name: ClassVar[str] = ""
    default_scope: ClassVar[str] = ""

    def __init__(self, config: ExternalProviderConfig) -> None:
        self.config = config

    @abstractmethod
    def authorize_url(
        self,
        *,
        state: str,
        code_challenge: str,
        redirect_uri: str,
        scope: str | None = None,
    ) -> str:
        """Return the PKCE authorize URL (S256 only)."""

    @abstractmethod
    def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> ExternalTokenResponse:
        """Redeem the auth code for tokens."""

    @abstractmethod
    def refresh(self, refresh_token: str) -> ExternalTokenResponse:
        """Exchange a refresh token for a fresh access token."""

    def describe(self) -> dict[str, Any]:
        return {
            "slug": self.provider_slug,
            "display_name": self.display_name or self.provider_slug,
            "authorize_endpoint": self.config.authorize_endpoint,
            "token_endpoint": self.config.token_endpoint,
            "default_scope": self.config.default_scope or self.default_scope,
        }


# ---------------------------------------------------------------------------
# Registry walks
# ---------------------------------------------------------------------------


def list_external_oauth_providers() -> dict[str, type[ExternalOAuthProvider]]:
    """Return ``{slug: class}`` for every registered provider."""
    from aqp.core.registry import list_by_kind

    out: dict[str, type[ExternalOAuthProvider]] = {}
    for alias, cls in list_by_kind(EXTERNAL_OAUTH_PROVIDER_KIND).items():
        if isinstance(cls, type) and issubclass(cls, ExternalOAuthProvider):
            slug = str(getattr(cls, "provider_slug", "")).lower()
            if slug:
                out[slug] = cls
    return out


def get_external_oauth_provider(slug: str) -> type[ExternalOAuthProvider]:
    providers = list_external_oauth_providers()
    cls = providers.get(slug.lower())
    if cls is None:
        raise ExternalOAuthProviderError(
            f"no external OAuth provider registered for slug={slug!r}"
        )
    return cls


__all__ = [
    "EXTERNAL_OAUTH_PROVIDER_KIND",
    "ExternalOAuthProvider",
    "ExternalOAuthProviderError",
    "ExternalOAuthProviderMeta",
    "ExternalProviderConfig",
    "ExternalTokenResponse",
    "get_external_oauth_provider",
    "list_external_oauth_providers",
]
