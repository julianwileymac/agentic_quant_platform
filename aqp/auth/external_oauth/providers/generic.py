"""Generic OAuth2 provider implementation (Workstream D).

Implements the standards-compliant Authorization Code with PKCE
(S256) flow for any external OAuth2 server. Per-vendor subclasses
under :mod:`aqp.auth.external_oauth.providers.{github,...}` inherit
from this and override only what differs.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

from aqp.auth.external_oauth.protocol import (
    ExternalOAuthProvider,
    ExternalOAuthProviderError,
    ExternalTokenResponse,
)

logger = logging.getLogger(__name__)


class GenericExternalOAuthProvider(ExternalOAuthProvider):
    """Standards-compliant OAuth2 provider — the base for everything else."""

    provider_slug = "generic"
    provider_alias = "GenericExternalOAuthProvider"
    display_name = "Generic OAuth2"

    def authorize_url(
        self,
        *,
        state: str,
        code_challenge: str,
        redirect_uri: str,
        scope: str | None = None,
    ) -> str:
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        eff_scope = scope or self.config.default_scope or self.default_scope
        if eff_scope:
            params["scope"] = eff_scope
        if self.config.audience:
            params["audience"] = self.config.audience
        if self.config.extra_params:
            params.update({str(k): str(v) for k, v in self.config.extra_params.items()})
        endpoint = self.config.authorize_endpoint
        if not endpoint:
            raise ExternalOAuthProviderError(
                f"{self.provider_slug}: authorize_endpoint is not configured"
            )
        sep = "&" if "?" in endpoint else "?"
        return f"{endpoint}{sep}{urlencode(params)}"

    def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> ExternalTokenResponse:
        return self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
                "client_id": self.config.client_id,
                **({"client_secret": self.config.client_secret} if self.config.client_secret else {}),
            }
        )

    def refresh(self, refresh_token: str) -> ExternalTokenResponse:
        if not refresh_token:
            raise ExternalOAuthProviderError("refresh_token is empty")
        return self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.config.client_id,
                **({"client_secret": self.config.client_secret} if self.config.client_secret else {}),
            }
        )

    def _token_request(self, body: dict[str, Any]) -> ExternalTokenResponse:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise ExternalOAuthProviderError("httpx is required for token exchange") from exc

        endpoint = self.config.token_endpoint
        if not endpoint:
            raise ExternalOAuthProviderError(
                f"{self.provider_slug}: token_endpoint is not configured"
            )
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    endpoint,
                    data=body,
                    headers={"Accept": "application/json"},
                )
        except Exception as exc:  # noqa: BLE001
            raise ExternalOAuthProviderError(f"token endpoint unreachable: {exc}") from exc
        if resp.status_code >= 400:
            raise ExternalOAuthProviderError(
                f"token endpoint returned {resp.status_code}: {resp.text[:200]}"
            )
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise ExternalOAuthProviderError(
                f"token endpoint returned non-JSON: {resp.text[:200]}"
            ) from exc
        return ExternalTokenResponse(
            access_token=str(data.get("access_token") or ""),
            refresh_token=str(data.get("refresh_token") or ""),
            expires_in=int(data.get("expires_in")) if data.get("expires_in") is not None else None,
            token_type=str(data.get("token_type") or "Bearer"),
            scope=str(data.get("scope") or ""),
            raw=data,
        )


__all__ = ["GenericExternalOAuthProvider"]
