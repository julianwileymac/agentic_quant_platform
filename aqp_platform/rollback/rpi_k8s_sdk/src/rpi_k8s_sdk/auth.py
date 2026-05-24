"""Auth0-aware HTTP client wrapper for the management SDK.

Reads ``RPI_MGMT_AUTH_TOKEN`` from the environment (or an explicit
``token`` arg) and attaches it as a Bearer header on every call. The
helper is intentionally thin — production callers should pass the
token explicitly so token lifetime is observable, but the env var
fallback keeps Cursor IDE integrations and Cloud Shells working
without changes.

The matching backend dep
(:func:`management.backend.src.auth.require_authenticated_mgmt`)
validates the token against the same Auth0 tenant + audience pair
AQP uses, so a single Auth0 Application can drive both surfaces.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


_ENV_VAR = "RPI_MGMT_AUTH_TOKEN"


@dataclass
class ManagementAuth:
    """Bundles the management API base URL + Auth0 token + tenancy headers."""

    base_url: str
    token: str | None = None
    extra_headers: dict[str, str] | None = None

    @classmethod
    def from_env(cls, *, base_url: str | None = None) -> "ManagementAuth":
        """Build from env vars: ``RPI_MGMT_BASE_URL`` + ``RPI_MGMT_AUTH_TOKEN``."""
        return cls(
            base_url=(
                base_url
                or os.environ.get("RPI_MGMT_BASE_URL", "")
                or "http://localhost:8080"
            ),
            token=os.environ.get(_ENV_VAR) or None,
        )

    def headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.extra_headers:
            headers.update(self.extra_headers)
        return headers

    def client(self, **kwargs: Any) -> httpx.Client:
        """Construct an authenticated :class:`httpx.Client` for this auth."""
        merged = dict(kwargs)
        merged.setdefault("base_url", self.base_url)
        client = httpx.Client(**merged)
        # Inject the headers via the default headers list rather than
        # overwriting per-request so callers can layer their own.
        for key, value in self.headers().items():
            client.headers[key] = value
        return client


__all__ = ["ManagementAuth"]
