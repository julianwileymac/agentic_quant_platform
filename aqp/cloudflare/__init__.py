"""Cloudflare edge integration (Phase D of the Management Engine).

The in-AQP Cloudflare layer mirrors the shape of
:mod:`aqp.kubernetes`:

- :class:`CloudflareClient` — single sanctioned API client, credentials
  via :class:`aqp.credentials.CredentialResolver`.
- :class:`CloudflareEdgeAdapter` — pluggable adapter with tunnel /
  Access app / DNS CRUD. Used by:
  - ``aqp/api/routes/cloudflare.py`` (REST)
  - ``aqp/data/mcp/tools/cloudflare.py`` (DataMCP)
  - ``aqp/auth/providers/cloudflare_access.py`` (JWKS / Access JWT
    validation reuses the same client).

AGENTS rule 26 — every external credential resolution goes through the
:class:`CredentialResolver` chain. The Cloudflare API token is registered
under the ``cloudflare:api_token`` key.
"""
from __future__ import annotations

from aqp.cloudflare.adapter import (
    AccessAppSummary,
    CloudflareAdapterError,
    CloudflareAdapterUnavailable,
    CloudflareEdgeAdapter,
    DnsRecordSummary,
    TunnelSummary,
    get_cloudflare_adapter,
    reset_cloudflare_adapter,
)
from aqp.cloudflare.client import CloudflareClient, get_cloudflare_client

__all__ = [
    "AccessAppSummary",
    "CloudflareAdapterError",
    "CloudflareAdapterUnavailable",
    "CloudflareClient",
    "CloudflareEdgeAdapter",
    "DnsRecordSummary",
    "TunnelSummary",
    "get_cloudflare_adapter",
    "get_cloudflare_client",
    "reset_cloudflare_adapter",
]
