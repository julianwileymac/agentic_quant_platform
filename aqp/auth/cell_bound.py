"""Cell-Bound-Authorization tokens for cross-cell MCP calls.

Phase 5 §8.5 (RESTRUCTURING_PLAN.md). Cross-cell calls are the
highest-risk path. This module mints + verifies short-lived
audience-bound JWTs that the ``aqp-edge`` (Envoy) cell router
validates BEFORE forwarding a request from cell A to cell B.

Wire shape::

    Source cell (cell-shared-std-us-east-1a)
       │
       │ outbound MCP call to cell-silo-reg-acme
       │
       │ HTTP headers:
       │   Authorization: Bearer <delegated-agent-jwt>   (existing)
       │   X-Biscuit: <attenuated-biscuit>               (Phase 5 §8.2)
       │   Cell-Bound-Authorization: <cba-jwt>           (Phase 5 §8.5)
       ▼
    aqp-edge (Envoy) at the destination cell
       │
       │ ext_authz validates the CBA-JWT:
       │   iss = "cell-shared-std-us-east-1a"   (verbatim cell id)
       │   aud = "cell-silo-reg-acme"           (verbatim cell id)
       │   nbf <= now <= exp (60-second window)
       ▼
    cell-silo-reg-acme/aqp-data-mcp-tenant_acme

The CBA-JWT is signed by the source cell's SPIFFE-issued workload
SVID (Phase 4 §7.2) — that's what binds the token to a specific
source workload, not just a generic AQP service. This is why
``Cell-Bound-Authorization`` is a SEPARATE header from
``Authorization``: the cell router validates it with the source
cell's public key (loaded from the cells registry), not the user
JWT's issuer.

The mint helper here is dependency-light: it produces the JWT but
defers the actual signing to a ``private_key_pem`` parameter the
caller fetches from the SPIFFE library or the Vault PKI. The verify
helper is the symmetric counterpart used by the cell router.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# Header name. Verbatim per the plan §8.5 — separate from
# ``Authorization`` so Envoy can validate it on the request path
# without parsing the user JWT.
CELL_BOUND_HEADER = "Cell-Bound-Authorization"

# Token lifetime — fixed at 60s per the plan. Long enough to absorb
# clock skew; short enough that an exfiltrated CBA expires before it
# can be replayed.
CBA_TTL_SECONDS = 60


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CellBoundError(RuntimeError):
    """Raised when CBA mint or verify fails."""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CellBoundClaims:
    """Decoded payload from a verified Cell-Bound-Authorization token."""

    iss: str  # cell-<source-cell-id>
    aud: str  # cell-<destination-cell-id>
    sub: str  # SPIFFE id of the source workload
    nbf: int
    exp: int
    iat: int
    jti: str
    request_id: str | None = None
    raw: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Mint
# ---------------------------------------------------------------------------


def mint(
    *,
    source_cell_id: str,
    destination_cell_id: str,
    workload_spiffe_id: str,
    private_key_pem: str,
    request_id: str | None = None,
) -> str:
    """Mint a CBA-JWT for one cross-cell call.

    The caller resolves ``private_key_pem`` from the local SPIFFE
    Workload API (Phase 4 §7.2). For test paths that don't have
    SPIFFE wired, callers can pass any ed25519 private key — the
    receiving cell's verify path uses the corresponding public key
    from the cells registry.
    """
    if source_cell_id == destination_cell_id:
        raise CellBoundError(
            "Cell-Bound-Authorization is for CROSS-cell calls only"
        )

    try:
        from jose import jwt as jose_jwt  # type: ignore[import-untyped]
    except ImportError as exc:
        raise CellBoundError(
            "python-jose not installed; pip install python-jose[cryptography]"
        ) from exc

    now = int(time.time())
    # ``source_cell_id`` and ``destination_cell_id`` are the verbatim
    # cells-registry ids (which already begin with ``cell-`` per the
    # Phase 3 §6.2 naming convention). We use them as-is so the JWT's
    # iss/aud match the canonical cell id strings reviewers expect to
    # see in audit logs.
    claims: dict[str, Any] = {
        "iss": source_cell_id,
        "aud": destination_cell_id,
        "sub": workload_spiffe_id,
        "nbf": now - 5,  # absorb clock skew
        "iat": now,
        "exp": now + CBA_TTL_SECONDS,
        "jti": str(uuid.uuid4()),
    }
    if request_id:
        claims["request_id"] = request_id

    try:
        return jose_jwt.encode(
            claims,
            private_key_pem,
            algorithm="EdDSA",
        )
    except Exception as exc:  # noqa: BLE001
        # Fall back to RS256 when the key isn't ed25519 — RS256 is
        # the MUST-SUPPORT algorithm for OIDC and works with both
        # PEM-encoded RSA and DER-encoded keys.
        try:
            return jose_jwt.encode(claims, private_key_pem, algorithm="RS256")
        except Exception as exc2:  # noqa: BLE001
            raise CellBoundError(
                f"CBA mint failed (EdDSA: {exc}; RS256: {exc2})"
            ) from exc2


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def verify(
    token: str,
    *,
    expected_destination_cell_id: str,
    public_key_pem: str,
    expected_source_cell_id: str | None = None,
) -> CellBoundClaims:
    """Validate a CBA-JWT against the expected source/destination tuple.

    Raises :class:`CellBoundError` on any failure (signature,
    audience, issuer, expiry, missing claims).
    """
    try:
        from jose import jwt as jose_jwt  # type: ignore[import-untyped]
        from jose.exceptions import JWTError  # type: ignore[import-untyped]
    except ImportError as exc:
        raise CellBoundError(
            "python-jose not installed; pip install python-jose[cryptography]"
        ) from exc

    # Same convention as :func:`mint` — both ids are passed verbatim.
    audience = expected_destination_cell_id
    issuer = expected_source_cell_id if expected_source_cell_id else None

    try:
        # python-jose raises if any required claim is missing.
        payload = jose_jwt.decode(
            token,
            public_key_pem,
            algorithms=["EdDSA", "RS256"],
            audience=audience,
            issuer=issuer,
            options={
                "require": ["exp", "iat", "nbf", "aud", "iss", "sub", "jti"],
                "verify_aud": True,
                "verify_iss": issuer is not None,
                "verify_exp": True,
                "verify_signature": True,
            },
        )
    except JWTError as exc:
        raise CellBoundError(f"CBA verify failed: {exc}") from exc

    return CellBoundClaims(
        iss=str(payload.get("iss")),
        aud=str(payload.get("aud")),
        sub=str(payload.get("sub")),
        nbf=int(payload.get("nbf") or 0),
        exp=int(payload.get("exp") or 0),
        iat=int(payload.get("iat") or 0),
        jti=str(payload.get("jti") or ""),
        request_id=payload.get("request_id"),
        raw=payload,
    )


__all__ = [
    "CBA_TTL_SECONDS",
    "CELL_BOUND_HEADER",
    "CellBoundClaims",
    "CellBoundError",
    "mint",
    "verify",
]
