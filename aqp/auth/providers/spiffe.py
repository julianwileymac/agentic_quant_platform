"""SPIFFE workload identity provider.

Phase 4 §7.2 (RESTRUCTURING_PLAN.md). The current ``M2MTokenIssuer``
mints short-lived JWTs via the Auth0 / Entra ``client_credentials``
grant, but those tokens are still bearer credentials —
exfiltrate the JWT and you can replay it from anywhere until expiry.

SPIFFE-bound identities (SVIDs) are workload-attested via the platform
(UID, cgroup, selectors) — much harder to steal and automatically
rotated. The SPIFFE Server validates the workload's identity at the
node level via the SPIRE Agent's Workload Attestor, then issues a
JWT-SVID or X.509-SVID over the Workload API Unix socket.

This module provides a :class:`SpiffeIdentityProvider` that
implements the existing :class:`IdentityProvider` interface so the
``M2MTokenIssuer`` can dispatch to it via the registry. Only the
``m2m_token`` method does real work — the user-flow methods
(:meth:`login_url`, :meth:`exchange_code`, ...) raise
:class:`NotImplementedError` because SPIFFE is workload-only.

Wiring (operator-side):

- Deploy SPIRE Server + Agent per cell (Phase 4 §7.2 K8s manifests
  at ``aqp_platform/deployments/kubernetes/cells/<cell-id>/spire/``).
- The SPIRE Agent exposes the Workload API on
  ``/run/spire/sockets/agent.sock`` mounted into every workload pod.
- Set ``AQP_AUTH_M2M_PROVIDER=spiffe`` to route ``M2MTokenIssuer``
  through this provider instead of Auth0. Pair Auth0 / Entra as the
  user-facing provider unchanged.

The implementation degrades cleanly when ``spiffe`` (the Python
SPIFFE library) is not installed or the Workload API socket isn't
reachable; the M2M issuer then falls through to the next provider in
the chain.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any

from aqp.auth.providers.protocol import (
    IdentityProvider,
    IdentityProviderConfig,
    IdentityProviderError,
    M2MTokenResult,
    TokenResponse,
)

logger = logging.getLogger(__name__)


# Default SPIFFE Workload API endpoint inside the pod. SPIRE Agent
# mounts ``/run/spire/sockets/agent.sock`` via the
# ``csi-driver-spiffe`` DaemonSet; older deployments use
# ``/spiffe-workload-api/spire-agent.sock``. Operators override via
# ``SPIFFE_ENDPOINT_SOCKET`` per the SPIFFE spec.
_DEFAULT_WORKLOAD_API_SOCKET = "unix:///run/spire/sockets/agent.sock"


# ---------------------------------------------------------------------------
# Cached JWT-SVID
# ---------------------------------------------------------------------------


@dataclass
class _CachedSvid:
    token: str
    audience: tuple[str, ...]
    expires_at: float


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class SpiffeIdentityProvider(IdentityProvider):
    """SPIFFE / SPIRE Workload API identity provider.

    Workload-only — the user-flow methods are unimplemented because
    SPIFFE is not an OIDC AS. The matching trust domain + audience
    layout is documented at
    ``aqp_docs/docs/concepts/identity/spiffe-workload-identity.md``.
    """

    provider_kind = "spiffe"
    provider_alias = "SpiffeIdentityProvider"

    def __init__(self, config: IdentityProviderConfig) -> None:
        super().__init__(config)
        self._lock = threading.RLock()
        self._cache: dict[tuple[str, ...], _CachedSvid] = {}

    # ------------------------------------------------------------------
    # IdentityProvider — workload-only stubs
    # ------------------------------------------------------------------

    def discovery(self) -> dict[str, Any]:
        # SPIFFE doesn't expose an OIDC discovery doc; surface the
        # trust-domain + workload-api socket so the diagnostics
        # endpoint can render meaningful state.
        return {
            "trust_domain": self.config.issuer,
            "audience": self.config.audience,
            "workload_api_socket": self._socket(),
        }

    def jwks(self) -> dict[str, Any]:
        # JWT-SVIDs are signed by the SPIFFE Server; the trust-domain
        # bundle is exposed via the Workload API's
        # ``FetchJWTBundles`` RPC. We expose an empty dict here and
        # rely on the SPIFFE library's internal validation when other
        # workloads validate our SVIDs.
        return {"keys": []}

    def login_url(self, **_kwargs: Any) -> str:  # type: ignore[override]
        raise NotImplementedError(
            "SpiffeIdentityProvider is workload-only; configure Auth0 / "
            "Entra for user-facing OIDC and SPIFFE for M2M."
        )

    def exchange_code(self, **_kwargs: Any) -> TokenResponse:  # type: ignore[override]
        raise NotImplementedError("SpiffeIdentityProvider is workload-only")

    def refresh(self, refresh_token: str) -> TokenResponse:  # noqa: ARG002
        raise NotImplementedError("SpiffeIdentityProvider is workload-only")

    def logout_url(self, **_kwargs: Any) -> str:  # type: ignore[override]
        raise NotImplementedError("SpiffeIdentityProvider is workload-only")

    # ------------------------------------------------------------------
    # The one method that does real work
    # ------------------------------------------------------------------

    def m2m_token(
        self,
        *,
        audience: str | None = None,
        scope: str | None = None,  # noqa: ARG002 - SPIFFE doesn't carry scope
    ) -> M2MTokenResult:
        """Fetch a JWT-SVID for the requested audience.

        The audience defaults to :attr:`IdentityProviderConfig.audience`
        when the caller doesn't override. Multiple audiences can be
        embedded in a single JWT-SVID; we pass exactly one here to keep
        the audience contract per-call.
        """
        aud = audience or self.config.audience or ""
        if not aud:
            raise IdentityProviderError(
                "spiffe: no audience provided (set AQP_AUTH_M2M_AUDIENCE "
                "or pass audience= explicitly)"
            )
        audiences: tuple[str, ...] = (aud,)
        cached = self._get_cached(audiences)
        if cached is not None:
            remaining = max(0, int(cached.expires_at - time.time()))
            return M2MTokenResult(
                access_token=cached.token,
                expires_in=remaining,
                token_type="Bearer",
                scope=None,
            )

        try:
            from spiffe.workloadapi import default_jwt_source  # type: ignore[import-untyped]
        except ImportError as exc:
            raise IdentityProviderError(
                "spiffe Python library not installed; pip install 'spiffe>=1.0' "
                "or pip install -e '.[auth]' (Phase 4 §7.2 added it)"
            ) from exc

        # Use the default JWT source which reads SPIFFE_ENDPOINT_SOCKET
        # from the environment if set; otherwise our explicit override.
        socket = self._socket()
        prev_socket = os.environ.get("SPIFFE_ENDPOINT_SOCKET")
        os.environ["SPIFFE_ENDPOINT_SOCKET"] = socket
        try:
            try:
                source = default_jwt_source.DefaultJwtSource()
            except Exception as exc:  # noqa: BLE001
                raise IdentityProviderError(
                    f"spiffe: workload api unreachable at {socket}: {exc}"
                ) from exc
            try:
                svid = source.fetch_svid(audiences=list(audiences))
            except Exception as exc:  # noqa: BLE001
                raise IdentityProviderError(
                    f"spiffe: fetch_svid raised: {exc}"
                ) from exc
            finally:
                try:
                    source.close()
                except Exception:  # noqa: BLE001
                    pass
        finally:
            if prev_socket is None:
                os.environ.pop("SPIFFE_ENDPOINT_SOCKET", None)
            else:
                os.environ["SPIFFE_ENDPOINT_SOCKET"] = prev_socket

        token = getattr(svid, "token", None) or getattr(svid, "raw", None)
        if not token:
            raise IdentityProviderError(
                "spiffe: fetched SVID has no token field"
            )
        # Expiry is exposed on the SVID; fall back to a conservative
        # 5-minute window if the library doesn't surface it.
        expiry = getattr(svid, "expiry", None) or getattr(svid, "expires_at", None)
        if expiry is None:
            expires_at = time.time() + 300
            expires_in = 300
        else:
            try:
                expires_at = float(expiry.timestamp()) if hasattr(expiry, "timestamp") else float(expiry)
            except Exception:  # noqa: BLE001
                expires_at = time.time() + 300
            expires_in = max(0, int(expires_at - time.time()))

        self._put_cached(audiences, _CachedSvid(token=token, audience=audiences, expires_at=expires_at))
        return M2MTokenResult(
            access_token=token,
            expires_in=expires_in,
            token_type="Bearer",
            scope=None,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _socket(self) -> str:
        return (
            os.environ.get("AQP_AUTH_SPIFFE_WORKLOAD_API_SOCKET", "")
            or os.environ.get("SPIFFE_ENDPOINT_SOCKET", "")
            or _DEFAULT_WORKLOAD_API_SOCKET
        )

    def _get_cached(self, audiences: tuple[str, ...]) -> _CachedSvid | None:
        with self._lock:
            cached = self._cache.get(audiences)
            if cached is None:
                return None
            # Refresh slightly before expiry so callers never see a
            # token that's about to expire.
            if cached.expires_at - time.time() < 30:
                self._cache.pop(audiences, None)
                return None
            return cached

    def _put_cached(self, audiences: tuple[str, ...], svid: _CachedSvid) -> None:
        with self._lock:
            self._cache[audiences] = svid

    def describe(self) -> dict[str, Any]:
        out = super().describe()
        out.update(
            {
                "trust_domain": self.config.issuer,
                "workload_api_socket": self._socket(),
                "cached_audiences": [
                    list(aud) for aud in self._cache
                ],
            }
        )
        return out


__all__ = ["SpiffeIdentityProvider"]
