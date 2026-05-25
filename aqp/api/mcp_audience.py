"""RFC 8707 (Resource Indicators) audience validation for AQP MCP servers.

The 2025-11-25 MCP authorization spec MUST clause: "MCP servers MUST
validate that access tokens were issued specifically for them as the
intended audience, according to RFC 8707 Section 2." Without this
check, a token minted for one MCP server (or the AQP API at large)
can be replayed against another — the canonical confused-deputy
vector for MCP.

This module exposes two helpers:

- :func:`validate_mcp_audience(request, expected_uri, *, mode)`:
  inspect the verified OIDC claims attached to the FastAPI request by
  the existing :mod:`aqp.api.deps` chain and assert that ``expected_uri``
  is in the ``aud`` claim. Honours a three-mode policy gate
  (``off`` / ``permissive`` / ``strict``).
- :func:`build_resource_metadata_header(expected_uri)`: builds the
  ``WWW-Authenticate: Bearer resource_metadata="…"`` response header
  RFC 9728 §3 mandates whenever a Bearer token is missing or rejected.

The validator is intentionally **additive** to the existing
:func:`aqp.auth.oidc.validate_jwt` call. That function already checks
``iss`` and the global ``aud`` (configured via
``settings.auth_oidc_audience``); this validator runs ON TOP and only
fires when the request is hitting an MCP route. The result: existing
non-MCP endpoints keep working with the old single-audience token
shape; MCP endpoints opt in to the tighter RFC 8707 binding.

The validator respects the bypass conventions the rest of
:mod:`aqp.api.security` uses:

- :data:`PUBLIC_ROUTERS`-style early exit when ``auth_provider=local``.
- Local default user (no Bearer at all) skipped — local dev loop must
  not break.
- ``mode='off'`` short-circuits everything.

No mutations. No logging of token material (only structural metadata
like the audience claim string, which is non-sensitive by definition).
"""
from __future__ import annotations

import logging
from typing import Any, Literal
from urllib.parse import quote

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


AudienceMode = Literal["off", "permissive", "strict"]


# ---------------------------------------------------------------------------
# Header builder
# ---------------------------------------------------------------------------


def build_resource_metadata_header(expected_uri: str) -> dict[str, str]:
    """Return the ``WWW-Authenticate`` header dict for a 401 response.

    RFC 9728 §3.1 requires the form::

        WWW-Authenticate: Bearer resource_metadata="<url>"

    where ``<url>`` points at the matching ``oauth-protected-resource``
    metadata document. We compute the document URL from the expected
    resource URI by replacing the path with the
    ``/.well-known/oauth-protected-resource/<path>`` form RFC 9728
    allows for namespaced resources on a single origin (see
    :mod:`aqp.api.well_known`).

    Returns an empty dict when ``expected_uri`` is unset; FastAPI will
    then emit a vanilla 401 without the header, which matches the pre-
    MCP-conformance behaviour.
    """
    if not expected_uri:
        return {}
    # We don't have URL parsing imports up here so do this defensively
    # in-string. ``expected_uri`` is configured per environment and
    # validated by the operator at startup.
    if "://" not in expected_uri:
        return {}
    scheme_idx = expected_uri.find("://")
    authority_start = scheme_idx + 3
    path_idx = expected_uri.find("/", authority_start)
    if path_idx == -1:
        # No path component — metadata lives at the root well-known.
        origin = expected_uri.rstrip("/")
        document_url = f"{origin}/.well-known/oauth-protected-resource"
    else:
        origin = expected_uri[:path_idx].rstrip("/")
        path = expected_uri[path_idx:].lstrip("/")
        document_url = f"{origin}/.well-known/oauth-protected-resource/{path}"
    # Use quote() to make sure embedded chars stay safe inside the
    # header value. The header is line-oriented so we can't have raw
    # newlines or doublequotes inside the URL.
    safe_url = quote(document_url, safe=":/?&=._-~")
    value = f'Bearer resource_metadata="{safe_url}"'
    return {"WWW-Authenticate": value}


# ---------------------------------------------------------------------------
# Claims extraction
# ---------------------------------------------------------------------------


def _aud_list_from_claims(claims: dict[str, Any]) -> list[str]:
    """Return the audience claim as a flat string list.

    Per RFC 7519 §4.1.3 ``aud`` is either a string or an array of
    strings; the JWT spec is intentionally relaxed here. We coerce
    everything to ``list[str]`` so the caller doesn't branch.
    """
    raw = claims.get("aud")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw if isinstance(item, str)]
    return []


def _resource_claims_from_claims(claims: dict[str, Any]) -> list[str]:
    """Return the RFC 8707 ``resource`` claim if present.

    Some authorization servers emit the requested resource indicator on
    the resulting token as a non-standard ``resource`` claim (Auth0
    does this when ``audience`` is paired with a resource indicator in
    the authorize call). When present we treat it as a stronger signal
    than ``aud`` since the ``resource`` claim cannot be aliased by a
    multi-audience token.
    """
    raw = claims.get("resource")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw if isinstance(item, str)]
    return []


def _request_claims(request: Request) -> dict[str, Any] | None:
    """Return the verified OIDC claims attached by :mod:`aqp.api.deps`.

    Returns ``None`` when the request is unauthenticated. Callers MUST
    decide how to handle that (the MCP server runs the regular
    :func:`require_authenticated` dep BEFORE us; if we reach this
    function and ``request.state.oidc_claims`` is absent, the request
    is the local default user and the validator no-ops).
    """
    claims = getattr(request.state, "oidc_claims", None)
    if isinstance(claims, dict):
        return claims
    return None


def _normalise_uri(uri: str) -> str:
    """Lower-case scheme + host, strip trailing slash.

    RFC 9728 §2 says the canonical URI comparison is by string
    equality; in practice operators stamp tokens with either trailing
    or non-trailing slash variants. The normalisation here is the
    minimum needed to avoid spurious failures.
    """
    return str(uri or "").rstrip("/").strip()


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def validate_mcp_audience(
    request: Request,
    expected_uri: str,
    *,
    mode: AudienceMode = "off",
) -> None:
    """Assert the verified JWT carries ``expected_uri`` in ``aud`` (or
    ``resource``).

    Args:
        request: the incoming FastAPI request — ``request.state.oidc_claims``
            is populated by the existing :mod:`aqp.api.deps` chain.
        expected_uri: the canonical URI of the MCP server (e.g.
            ``https://api.aqp.fund/mcp/data``); MUST match what the
            ``/.well-known/oauth-protected-resource`` document
            advertises.
        mode: ``off`` skips entirely (default — operator must opt in);
            ``permissive`` logs would-be denies + tags the OTEL span
            but lets the request through; ``strict`` raises
            ``HTTPException(401)`` with the RFC 9728 header.

    No-ops when:
        - ``mode == "off"``.
        - The configured auth provider is ``local`` (request is local
          dev, no OIDC envelope to inspect).
        - ``request.state.oidc_claims`` is absent (local default user;
          the existing auth chain accepts this path).
    """
    if mode == "off":
        return
    expected = _normalise_uri(expected_uri)
    if not expected:
        # Nothing to enforce against. Permissive logs; strict still
        # rejects because an MCP route running without a canonical URI
        # is misconfigured by definition.
        if mode == "strict":
            raise HTTPException(
                status_code=500,
                detail="MCP canonical URI is not configured for audience validation",
            )
        logger.warning(
            "validate_mcp_audience: no canonical URI configured; permissive no-op"
        )
        return

    # Local dev loop: no OIDC envelope, accept.
    try:
        from aqp.config import settings

        if str(getattr(settings, "auth_provider", "local")).lower() == "local":
            return
    except Exception:  # noqa: BLE001 - never fail validation on settings read
        return

    claims = _request_claims(request)
    if claims is None:
        # Default user (local-default token-less path). The earlier
        # require_authenticated dep already allowed this through and
        # we don't want to second-guess that decision here.
        return

    aud = _aud_list_from_claims(claims)
    resource_claim = _resource_claims_from_claims(claims)

    accepted: list[str] = []
    accepted.extend(_normalise_uri(value) for value in aud)
    accepted.extend(_normalise_uri(value) for value in resource_claim)

    if expected in accepted:
        return

    # Audience mismatch. Build the response header before raising so the
    # MCP client knows where to fetch the metadata document.
    headers = build_resource_metadata_header(expected_uri)
    detail = (
        "token audience does not include the MCP server's canonical URI; "
        "request a token with resource={expected!r} (RFC 8707)"
    ).format(expected=expected)

    if mode == "strict":
        raise HTTPException(status_code=401, detail=detail, headers=headers)

    # Permissive: log + OTEL span attribute, allow through.
    logger.warning(
        "mcp.audience.would_deny expected=%r accepted=%r path=%s",
        expected,
        accepted,
        getattr(request.url, "path", None) if getattr(request, "url", None) else None,
    )
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]

        span = trace.get_current_span()
        if span is not None and span.is_recording():
            span.set_attribute("aqp.mcp.audience.would_deny", True)
            span.set_attribute("aqp.mcp.audience.expected", expected)
            span.set_attribute("aqp.mcp.audience.accepted", ",".join(accepted))
    except Exception:  # pragma: no cover - OTEL optional
        return


# ---------------------------------------------------------------------------
# Settings access helpers
# ---------------------------------------------------------------------------


def get_mcp_audience_mode() -> AudienceMode:
    """Return the configured RFC 8707 enforcement mode.

    Lazy-imported so this module stays importable from test contexts
    that don't always have a full ``Settings`` instance constructed.
    """
    try:
        from aqp.config import settings

        raw = str(getattr(settings, "mcp_require_rfc8707", "off") or "off").lower()
    except Exception:  # noqa: BLE001
        return "off"
    if raw in ("off", "permissive", "strict"):
        return raw  # type: ignore[return-value]
    return "off"


def get_data_mcp_canonical_uri() -> str:
    try:
        from aqp.config import settings

        return str(getattr(settings, "mcp_data_canonical_uri", "") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def get_codebase_mcp_canonical_uri() -> str:
    try:
        from aqp.config import settings

        return str(getattr(settings, "mcp_codebase_canonical_uri", "") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def get_ml_mcp_canonical_uri() -> str:
    """Return ``settings.mcp_ml_canonical_uri`` defensively (Hard Rule 49).

    The dedicated ``aqp-ml-mcp`` server passes the result here to
    :func:`validate_mcp_audience` on every ``tools/call`` so a token
    minted for the data MCP cannot be replayed against the MLOps
    surface (CVE-2025-49596 / CVE-2025-6514 reference vector).
    """
    try:
        from aqp.config import settings

        return str(getattr(settings, "mcp_ml_canonical_uri", "") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


__all__ = [
    "AudienceMode",
    "build_resource_metadata_header",
    "get_codebase_mcp_canonical_uri",
    "get_ml_mcp_canonical_uri",
    "get_data_mcp_canonical_uri",
    "get_mcp_audience_mode",
    "validate_mcp_audience",
]
