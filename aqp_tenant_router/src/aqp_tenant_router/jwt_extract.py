"""JWT claim extraction for the tenant-router.

The router validates the JWT signature against the Auth0 / Entra
JWKS (when configured) and pulls out the three claims it routes
on: ``sub``, ``workspace_id``, and (optional) ``tenant_id``. Claim
namespacing follows the AQP convention (custom claims live under
``https://aqp.internal/`` per
``aqp_docs/docs/concepts/identity/index.md``).

When ``AQP_TENANT_ROUTER_JWKS_URI`` is unset the router accepts
unsigned tokens — that's the local-dev path and is gated by an
explicit settings flag in production.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JwtClaims:
    """Subset of JWT claims the router needs.

    ``sub`` is the authoritative user id. ``workspace_id`` and
    ``tenant_id`` are namespaced custom claims that come from the
    Auth0 / Entra rule pipeline (see
    ``aqp/api/routes/auth0_sync.py``). When the JWT carries neither,
    the router falls back to the default-workspace path and routes
    to the shared-std cell for the user's tier.
    """

    sub: str
    workspace_id: str | None = None
    tenant_id: str | None = None
    organization_id: str | None = None
    raw_claims: dict[str, Any] | None = None


_CLAIM_NAMESPACE = "https://aqp.internal/"


def extract_claims(token_payload: dict[str, Any]) -> JwtClaims:
    """Pull the routing claims out of a decoded JWT payload.

    Reads both namespaced and unnamespaced variants because the
    Auth0 Action and the Entra ID custom claims emitter format
    custom claims slightly differently. The router accepts either.
    """
    sub = str(token_payload.get("sub") or "")
    workspace_id = (
        token_payload.get(f"{_CLAIM_NAMESPACE}workspace_id")
        or token_payload.get("workspace_id")
        or token_payload.get("aqp_workspace_id")
    )
    tenant_id = (
        token_payload.get(f"{_CLAIM_NAMESPACE}tenant_id")
        or token_payload.get("tenant_id")
        or token_payload.get("aqp_tenant_id")
    )
    organization_id = (
        token_payload.get(f"{_CLAIM_NAMESPACE}organization_id")
        or token_payload.get("organization_id")
        or token_payload.get("aqp_org_id")
    )
    return JwtClaims(
        sub=sub,
        workspace_id=str(workspace_id) if workspace_id else None,
        tenant_id=str(tenant_id) if tenant_id else None,
        organization_id=str(organization_id) if organization_id else None,
        raw_claims=token_payload,
    )


def decode_unsigned(token: str) -> dict[str, Any]:
    """Decode a JWT WITHOUT signature validation. Local-dev only.

    Use :func:`decode_and_validate` in production. This helper exists
    so the smoke tests + the local Docker Compose path can avoid
    plumbing in a JWKS host.
    """
    from jose import jwt  # type: ignore[import-untyped]

    return jwt.get_unverified_claims(token)


def decode_and_validate(
    token: str,
    *,
    jwks: dict[str, Any],
    audience: str | None,
    issuer: str | None,
) -> dict[str, Any]:
    """Validate signature + standard claims and return the payload."""
    from jose import jwt  # type: ignore[import-untyped]

    return jwt.decode(
        token,
        jwks,
        audience=audience,
        issuer=issuer,
        options={"verify_at_hash": False},
    )


__all__ = ["JwtClaims", "decode_and_validate", "decode_unsigned", "extract_claims"]
