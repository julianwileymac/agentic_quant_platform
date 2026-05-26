"""Admin step-up MFA dependency.

Boundary-respectful shim that wraps :func:`require_admin_scope` with
an additional check that the bearer carries fresh MFA evidence per
RFC 9470 + AGENTS hard rule 52.

The admin BFF cannot import ``aqp.api.security_stepup`` (would break
the boundary in `.cursor/rules/aqp-admin.mdc`). Instead this dep
inspects the verified JWT payload directly for:

- ``amr`` claim intersecting the canonical MFA classes (``mfa``,
  ``otp``, ``hwk``, ``swk``, ``face``, ``fpt``, ``iris``); OR
- ``acr`` claim equal to ``urn:mace:incommon:iap:silver`` /
  ``http://schemas.openid.net/pape/policies/2007/06/multi-factor`` /
  ``mfa`` (Auth0 + Entra conventions).

AND the ``auth_time`` claim within the configured ``max_age_seconds``
window (default 180).

On failure the dep raises HTTP 401 with a RFC 9470 challenge so the
SPA's ``apiFetch`` middleware can pop the IdP for a fresh MFA token
and retry. Step-up is NEVER soft-failed even in
``AQP_AUTH_ENFORCE=permissive`` — the gate is a separate defence
layer from the scope check.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from fastapi import Depends, HTTPException, status

from aqp_admin.deps.identity import AdminUser, require_admin_scope

logger = logging.getLogger(__name__)


_MFA_AMR_VALUES = frozenset(
    {
        "mfa",
        "otp",
        "hwk",
        "swk",
        "face",
        "fpt",
        "iris",
        "kba",
        "pwd+otp",
        "pwd+hwk",
        "pwd+swk",
    }
)

_MFA_ACR_VALUES = frozenset(
    {
        "mfa",
        "urn:mace:incommon:iap:silver",
        "http://schemas.openid.net/pape/policies/2007/06/multi-factor",
        "http://schemas.openid.net/pape/policies/2007/06/multi-factor-physical",
    }
)


def _has_fresh_mfa(payload: dict[str, Any], *, max_age_seconds: int) -> tuple[bool, str]:
    """Return ``(ok, reason)`` describing the freshness check."""
    amr = payload.get("amr") or []
    if isinstance(amr, str):
        amr = [amr]
    amr_set = {str(a).lower() for a in amr}
    has_mfa_amr = bool(amr_set & _MFA_AMR_VALUES)

    acr = str(payload.get("acr") or "").lower()
    has_mfa_acr = acr in _MFA_ACR_VALUES

    if not (has_mfa_amr or has_mfa_acr):
        return (
            False,
            "missing MFA evidence (amr/acr claims do not assert multi-factor)",
        )

    auth_time = payload.get("auth_time")
    if auth_time is None:
        # When the IdP did not include auth_time, fall back to ``iat``
        # — Entra emits ``iat`` reliably; some Auth0 tenants omit
        # ``auth_time`` for refresh-flow tokens.
        auth_time = payload.get("iat")
    if auth_time is None:
        return False, "no auth_time / iat claim available"

    try:
        auth_time_int = int(auth_time)
    except (TypeError, ValueError):
        return False, "auth_time / iat is not a unix timestamp"

    age_seconds = int(time.time()) - auth_time_int
    if age_seconds < 0:
        # Clock skew tolerance — treat negative ages (token issued in
        # the near future) as fresh per the JwtValidator's leeway.
        age_seconds = 0
    if age_seconds > max_age_seconds:
        return (
            False,
            f"MFA evidence stale ({age_seconds}s > {max_age_seconds}s)",
        )
    return True, "ok"


def require_admin_step_up(
    *required_scopes: str,
    max_age_seconds: int = 180,
) -> Callable[..., AdminUser]:
    """FastAPI dep that enforces ``required_scopes`` AND step-up MFA.

    Usage::

        @router.post("/admin/secrets/{ref}/rotate")
        async def rotate_secret(
            user: AdminUser = Depends(
                require_admin_step_up("manage:infrastructure"),
            ),
        ): ...

    Equivalent to :func:`require_admin_scope` plus the freshness
    check — combine the two so callers don't accidentally drop
    step-up while reshuffling deps.
    """
    scope_dep = require_admin_scope(*required_scopes) if required_scopes else None

    async def _dep(
        user: AdminUser = (
            Depends(scope_dep) if scope_dep is not None else Depends(require_admin_scope())
        ),
    ) -> AdminUser:
        if user.is_anonymous:
            # Local dev anonymous user always passes; the auth_required
            # = False short-circuit in identity.py is the contract.
            return user

        ok, reason = _has_fresh_mfa(user.payload, max_age_seconds=max_age_seconds)
        if not ok:
            challenge = (
                f'Bearer error="insufficient_user_authentication", '
                f'error_description="{reason}", '
                f'acr_values="mfa", '
                f'max_age="{max_age_seconds}"'
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "insufficient_user_authentication",
                    "error_description": reason,
                    "acr_values": "mfa",
                    "max_age": max_age_seconds,
                },
                headers={"WWW-Authenticate": challenge},
            )
        return user

    return _dep


__all__ = ["require_admin_step_up"]
