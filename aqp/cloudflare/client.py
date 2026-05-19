"""Thin :class:`CloudflareClient` wrapper — single sanctioned Cloudflare API client.

Resolves the API token + account id via
:class:`aqp.credentials.CredentialResolver` (AGENTS rule 26) so the
operator can rotate the token by:

- env vars (``CLOUDFLARE_API_TOKEN`` / ``CLOUDFLARE_ACCOUNT_ID``), or
- file store (``~/.config/aqp/credentials/cloudflare.json``), or
- M2M issuer (when the rotation pipeline is wired).

Never imports the SDK at module level — the import is lazy so AQP keeps
installable without ``cloudflare`` in the environment.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any

from aqp.credentials import resolver as credential_resolver
from aqp.credentials.protocol import CredentialKey

logger = logging.getLogger(__name__)


_CLIENT_LOCK = threading.RLock()
_CLIENT_CACHE: dict[str, Any] = {}


class CloudflareClient:
    """Holds a configured ``cloudflare.Cloudflare`` SDK instance + account id.

    Pull this from :func:`get_cloudflare_client`; never construct
    directly — the helper threads through credential resolution,
    optional override, and the process-wide cache.
    """

    def __init__(
        self,
        *,
        api_token: str,
        account_id: str,
        client: Any,
    ) -> None:
        self._api_token = api_token
        self.account_id = account_id
        self.sdk = client

    @property
    def has_token(self) -> bool:
        return bool(self._api_token)

    @property
    def has_account(self) -> bool:
        return bool(self.account_id)

    def describe(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "has_token": self.has_token,
            "sdk": type(self.sdk).__module__ + "." + type(self.sdk).__name__,
        }


def _resolve_credentials() -> tuple[str, str]:
    """Pull ``(api_token, account_id)`` from the credential chain."""
    resolver = credential_resolver.get_resolver()
    payload = resolver.resolve(
        CredentialKey(service="cloudflare", purpose="api_token"),
        default={
            "api_token": os.environ.get("CLOUDFLARE_API_TOKEN", ""),
            "account_id": os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
        },
    )
    api_token = (payload.get("api_token") or "").strip()
    account_id = (payload.get("account_id") or "").strip()
    return api_token, account_id


def get_cloudflare_client(*, force_refresh: bool = False) -> CloudflareClient:
    """Return the process-wide :class:`CloudflareClient`.

    Lazily resolves credentials + lazily imports the ``cloudflare`` SDK
    so the AQP package keeps installable without it. Raises
    :class:`RuntimeError` when the token is missing — callers (the
    adapter / route / MCP tool) catch and translate to the appropriate
    error envelope.
    """
    with _CLIENT_LOCK:
        if not force_refresh and "client" in _CLIENT_CACHE:
            return _CLIENT_CACHE["client"]

        api_token, account_id = _resolve_credentials()
        if not api_token:
            raise RuntimeError(
                "Cloudflare API token missing (set CLOUDFLARE_API_TOKEN, "
                "wire ~/.config/aqp/credentials/cloudflare.json, or enable "
                "the M2M issuer)."
            )
        if not account_id:
            raise RuntimeError(
                "Cloudflare account id missing (set CLOUDFLARE_ACCOUNT_ID)."
            )

        try:
            from cloudflare import Cloudflare  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "cloudflare SDK not installed (pip install 'cloudflare>=4.0')"
            ) from exc

        sdk = Cloudflare(api_token=api_token)
        client = CloudflareClient(
            api_token=api_token, account_id=account_id, client=sdk
        )
        _CLIENT_CACHE["client"] = client
        return client


def reset_cloudflare_client() -> None:
    """Drop the cached client so the next access re-reads credentials."""
    with _CLIENT_LOCK:
        _CLIENT_CACHE.clear()


__all__ = [
    "CloudflareClient",
    "get_cloudflare_client",
    "reset_cloudflare_client",
]
