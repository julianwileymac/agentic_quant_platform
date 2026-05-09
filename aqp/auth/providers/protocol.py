"""IdentityProvider ABC + auto-registering metaclass.

Mirrors :class:`aqp.rl.core.base.RLComponentMeta` and
:class:`aqp.credentials.protocol.SecretStoreMeta`: subclasses set
``provider_kind`` (``auth0`` / ``oidc`` / ``mock``) and the metaclass
calls :func:`aqp.core.registry.register` automatically so introspection
endpoints can enumerate them without a manual decorator.

Public surface::

    from aqp.auth.providers import (
        IdentityProvider,
        IdentityProviderConfig,
        get_active_provider,
    )

    provider = get_active_provider()
    auth_url = provider.login_url(redirect_uri="...", state="...", code_challenge="...")
"""
from __future__ import annotations

import logging
import threading
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from aqp.core.registry import register

logger = logging.getLogger(__name__)


IDENTITY_PROVIDER_KIND = "identity_provider"


class IdentityProviderError(Exception):
    """Base class for provider-side failures (HTTP errors, missing config)."""


@dataclass(frozen=True)
class IdentityProviderConfig:
    """Per-provider config snapshot.

    ``issuer`` should be the full discovery URL prefix
    (``https://<tenant>.auth0.com`` or ``https://idp.example.com/realms/aqp``).
    ``audience`` is the resource the access token is intended for.
    ``client_id`` / ``client_secret`` are the OAuth confidential-client
    credentials this AQP service holds; the SPA client uses the public
    ``client_id`` only.
    ``logout_callback`` is the URL the provider redirects to after a
    user-initiated logout.
    """

    issuer: str
    audience: str
    client_id: str = ""
    client_secret: str = ""
    logout_callback: str = ""
    extra_authorize_params: dict[str, str] = field(default_factory=dict)

    def with_overrides(self, **kwargs: Any) -> IdentityProviderConfig:
        merged = {**self.__dict__, **kwargs}
        return IdentityProviderConfig(**merged)


@dataclass(frozen=True)
class TokenResponse:
    """Result of an authorization-code or refresh-token exchange."""

    access_token: str
    id_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int | None = None
    scope: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class M2MTokenResult:
    """Service-to-service access token from ``client_credentials``."""

    access_token: str
    expires_in: int
    token_type: str = "Bearer"
    scope: str | None = None


class IdentityProviderMeta(ABCMeta):
    """Metaclass that auto-registers concrete :class:`IdentityProvider` classes.

    Sets the alias from ``provider_alias`` (defaulting to the class
    name) and the registry kind to :data:`IDENTITY_PROVIDER_KIND`.
    Abstract bases (``__abstract_provider__ = True`` or names starting
    with ``Base`` / ``_``) are skipped.
    """

    def __new__(mcs, name, bases, namespace, **kwargs):  # type: ignore[override]
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if namespace.get("__abstract_provider__", False):
            return cls
        if name.startswith(("Base", "_")):
            return cls
        provider_kind = getattr(cls, "provider_kind", None)
        if not provider_kind:
            return cls
        alias = getattr(cls, "provider_alias", None) or cls.__name__
        try:
            register(name=alias, kind=IDENTITY_PROVIDER_KIND, source=str(provider_kind))(cls)
        except Exception:  # noqa: BLE001 - never fail import on registry hiccup
            logger.debug("IdentityProvider auto-registration failed for %s", name, exc_info=True)
        return cls


class IdentityProvider(metaclass=IdentityProviderMeta):
    """Pluggable OIDC-like identity provider.

    Subclasses set ``provider_kind`` (the dispatch key matched against
    ``settings.auth_provider``) and override the methods relevant to
    the provider's capabilities.

    The default implementations of :meth:`discovery`, :meth:`jwks`,
    :meth:`exchange_code`, :meth:`refresh`, and :meth:`m2m_token` use
    standard OIDC endpoints derived from the discovery document. Auth0
    overrides :meth:`logout_url` to use ``/v2/logout``; generic OIDC
    overrides it to use ``end_session_endpoint``.
    """

    __abstract_provider__: ClassVar[bool] = True

    provider_kind: ClassVar[str] = ""
    provider_alias: ClassVar[str | None] = None

    def __init__(self, config: IdentityProviderConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Capability surface
    # ------------------------------------------------------------------

    @abstractmethod
    def discovery(self) -> dict[str, Any]:
        """Return the cached ``.well-known/openid-configuration`` document."""

    @abstractmethod
    def jwks(self) -> dict[str, Any]:
        """Return the cached JSON Web Key Set."""

    @abstractmethod
    def login_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        code_challenge: str,
        scope: str = "openid profile email offline_access",
        audience: str | None = None,
    ) -> str:
        """Return the provider's authorization-code (PKCE) URL."""

    @abstractmethod
    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> TokenResponse:
        """Exchange the auth code for tokens."""

    @abstractmethod
    def refresh(self, refresh_token: str) -> TokenResponse:
        """Exchange a refresh token for a fresh access token."""

    @abstractmethod
    def logout_url(
        self,
        *,
        return_to: str | None = None,
        id_token_hint: str | None = None,
    ) -> str:
        """Return the provider's logout URL."""

    @abstractmethod
    def m2m_token(
        self,
        *,
        audience: str | None = None,
        scope: str | None = None,
    ) -> M2MTokenResult:
        """Mint a service-to-service token via the ``client_credentials`` grant."""

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def describe(self) -> dict[str, Any]:
        return {
            "kind": self.provider_kind,
            "alias": self.provider_alias or self.__class__.__name__,
            "issuer": self.config.issuer,
            "audience": self.config.audience,
            "has_client_secret": bool(self.config.client_secret),
        }


# ---------------------------------------------------------------------------
# Active provider singleton
# ---------------------------------------------------------------------------


_PROVIDER: IdentityProvider | None = None
_PROVIDER_LOCK = threading.RLock()


def list_provider_classes() -> dict[str, type[IdentityProvider]]:
    """Return ``{alias: class}`` for every registered provider."""
    from aqp.core.registry import list_by_kind

    out: dict[str, type[IdentityProvider]] = {}
    for alias, cls in list_by_kind(IDENTITY_PROVIDER_KIND).items():
        if isinstance(cls, type) and issubclass(cls, IdentityProvider):
            out[alias] = cls
    return out


def _select_provider_class(kind: str) -> type[IdentityProvider]:
    """Find the concrete class whose ``provider_kind`` matches ``kind``."""
    classes = list_provider_classes()
    for cls in classes.values():
        if str(getattr(cls, "provider_kind", "")).lower() == kind.lower():
            return cls
    # Mock is always available; fall back to it so tests never explode
    # because of a missing provider.
    for cls in classes.values():
        if str(getattr(cls, "provider_kind", "")).lower() == "mock":
            return cls
    raise IdentityProviderError(
        f"No identity provider registered for kind={kind!r}"
    )


def _build_active_provider() -> IdentityProvider:
    from aqp.config import settings

    provider_kind = (str(settings.auth_provider or "local").strip().lower() or "local")
    if provider_kind == "local":
        # Local mode = mock provider in this layer; the FastAPI deps
        # short-circuit local users before reaching the provider, so
        # this is effectively only a fallback for tests.
        provider_kind = "mock"

    config = IdentityProviderConfig(
        issuer=str(settings.auth_oidc_issuer or "").strip(),
        audience=str(settings.auth_oidc_audience or "").strip(),
        client_id=str(getattr(settings, "auth_oidc_client_id", "") or "").strip(),
        client_secret=str(getattr(settings, "auth_oidc_client_secret", "") or "").strip(),
        logout_callback=str(getattr(settings, "auth_logout_callback", "") or "").strip(),
    )
    cls = _select_provider_class(provider_kind)
    return cls(config)


def get_active_provider() -> IdentityProvider:
    """Return the process-wide active :class:`IdentityProvider`."""
    global _PROVIDER
    if _PROVIDER is None:
        with _PROVIDER_LOCK:
            if _PROVIDER is None:
                _PROVIDER = _build_active_provider()
    return _PROVIDER


def register_provider(provider: IdentityProvider) -> None:
    """Replace the active provider. Used by tests + the M3 wiring."""
    global _PROVIDER
    with _PROVIDER_LOCK:
        _PROVIDER = provider


def reset_active_provider() -> None:
    """Drop the active provider so the next ``get_active_provider`` rebuilds."""
    global _PROVIDER
    with _PROVIDER_LOCK:
        _PROVIDER = None


__all__ = [
    "IDENTITY_PROVIDER_KIND",
    "IdentityProvider",
    "IdentityProviderConfig",
    "IdentityProviderError",
    "IdentityProviderMeta",
    "M2MTokenResult",
    "TokenResponse",
    "get_active_provider",
    "list_provider_classes",
    "register_provider",
    "reset_active_provider",
]
