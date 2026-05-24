"""OAuth 2.0 Protected Resource Metadata (RFC 9728) for AQP MCP servers.

The 2025-11-25 MCP authorization spec mandates that every MCP server
expose a Protected Resource Metadata document at
``/.well-known/oauth-protected-resource`` (RFC 9728) so MCP clients can
discover the matching authorization server. The accompanying ``WWW-
Authenticate: Bearer resource_metadata=<url>`` header is emitted by the
MCP server on 401 responses (see :mod:`aqp.api.mcp_audience`).

This module exposes ONE FastAPI router with TWO routes:

- ``GET /.well-known/oauth-protected-resource`` — the canonical, root-
  scoped document covering the entire AQP backend.
- ``GET /.well-known/oauth-protected-resource/{resource_path:path}`` —
  per-resource documents. We use it to publish distinct metadata for
  the two MCP servers AQP hosts: the data MCP at ``/mcp/data`` and the
  codebase MCP at ``/mcp/codebase``. The 2025-11-25 spec (and RFC 9728
  §3.1) allows a resource server to namespace its metadata when one
  origin hosts multiple protected resources.

The document fields follow RFC 9728 §2:

- ``resource`` (required): the canonical URI of the protected resource.
- ``authorization_servers`` (recommended): array of issuer identifiers
  the client should use for token acquisition.
- ``scopes_supported`` (recommended): array of OAuth scope values the
  resource recognises.
- ``bearer_methods_supported``: ``["header"]`` since AQP only accepts
  ``Authorization: Bearer …``.
- ``resource_documentation``: pointer to operator-facing docs.

The canonical URIs come from the new ``Settings.mcp_data_canonical_uri``
and ``Settings.mcp_codebase_canonical_uri`` knobs (workstream E). They
intentionally default to ``""`` so production deployments must opt in
explicitly via environment.

No mutations. No secrets. The route is always public — RFC 9728 §6.1
explicitly states the metadata document MUST be publicly retrievable.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from aqp.config import settings

logger = logging.getLogger(__name__)


_BEARER_METHODS = ["header"]
_DOCUMENTATION_URL = "https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp_docs/data-mcp.md"


def _safe_origin() -> str:
    """Best-effort backend origin string for fallback ``resource`` URIs.

    Used only when both ``mcp_*_canonical_uri`` knobs are empty; in
    production the operator MUST set them so the audience-bound tokens
    minted by the authorization server match what the MCP server
    advertises here.
    """
    bind_url = getattr(settings, "backend_external_url", None) or ""
    return str(bind_url or "").rstrip("/")


def _data_mcp_uri() -> str:
    explicit = str(getattr(settings, "mcp_data_canonical_uri", "") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    origin = _safe_origin()
    if origin:
        return f"{origin}/mcp/data"
    return ""


def _codebase_mcp_uri() -> str:
    explicit = str(getattr(settings, "mcp_codebase_canonical_uri", "") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    origin = _safe_origin()
    if origin:
        return f"{origin}/mcp/codebase"
    return ""


def _authorization_servers() -> list[str]:
    """Return the configured issuer as a single-entry list when present.

    Per RFC 9728 §2 the ``authorization_servers`` field is an array; AQP
    today federates onto exactly one IdP at a time via the
    :class:`aqp.auth.providers.IdentityProvider` singleton, so the list
    has at most one element. The 2025-11-25 MCP spec recommends
    populating this field whenever discovery is non-trivial — a fresh
    MCP client would otherwise have to probe.
    """
    issuer = str(getattr(settings, "auth_oidc_issuer", "") or "").strip()
    if not issuer:
        return []
    return [issuer.rstrip("/")]


def _scopes_supported_data() -> list[str]:
    """Scopes the data MCP recognises.

    Intentionally aligned with the existing ``data:read`` / ``data:write``
    surface the FastAPI dep layer enforces today (see
    :mod:`aqp.api.security`). New scopes that appear on a
    :class:`DataMCPTool.required_scopes` SHOULD be added here so
    discovery-driven clients can pick them.
    """
    return ["data:read", "data:write", "agents:invoke", "admin:cluster"]


def _scopes_supported_codebase() -> list[str]:
    return ["code:read", "code:write", "agents:invoke"]


def _metadata_document(
    *,
    resource: str,
    scopes: list[str],
    description: str,
) -> dict[str, Any]:
    if not resource:
        # 404 surfaces here because emitting an empty ``resource`` would
        # be a protocol violation (RFC 9728 §2: ``resource`` is REQUIRED
        # and MUST be a URI). The operator's fix is to set
        # ``AQP_MCP_DATA_CANONICAL_URI`` / ``AQP_MCP_CODEBASE_CANONICAL_URI``.
        raise HTTPException(
            status_code=404,
            detail="MCP canonical URI is not configured",
        )
    return {
        "resource": resource,
        "authorization_servers": _authorization_servers(),
        "scopes_supported": scopes,
        "bearer_methods_supported": list(_BEARER_METHODS),
        "resource_name": description,
        "resource_documentation": _DOCUMENTATION_URL,
    }


def build_well_known_router() -> APIRouter:
    """Return a FastAPI router exposing RFC 9728 metadata documents.

    Mount once at app root in :mod:`aqp.api.main`. The router is
    deliberately public (no auth dep) — RFC 9728 §6.1 mandates
    unauthenticated retrieval so an MCP client can bootstrap.
    """
    router = APIRouter(prefix="/.well-known", tags=["well-known"])

    @router.get("/oauth-protected-resource", response_model=None)
    def root_metadata() -> dict[str, Any]:
        """Root-scoped metadata — covers the AQP backend as a whole.

        Returned when the audience of an incoming token is the AQP API
        rather than a specific MCP endpoint. Backwards-compatible with
        clients that don't yet understand the per-resource form below.
        """
        resource = _data_mcp_uri() or _codebase_mcp_uri() or _safe_origin()
        return _metadata_document(
            resource=resource,
            scopes=sorted(set(_scopes_supported_data() + _scopes_supported_codebase())),
            description="Agentic Quant Platform",
        )

    @router.get("/oauth-protected-resource/mcp/data", response_model=None)
    def data_mcp_metadata() -> dict[str, Any]:
        return _metadata_document(
            resource=_data_mcp_uri(),
            scopes=_scopes_supported_data(),
            description="AQP Data MCP",
        )

    @router.get("/oauth-protected-resource/mcp/codebase", response_model=None)
    def codebase_mcp_metadata() -> dict[str, Any]:
        return _metadata_document(
            resource=_codebase_mcp_uri(),
            scopes=_scopes_supported_codebase(),
            description="AQP Codebase MCP",
        )

    return router


__all__ = [
    "build_well_known_router",
]
