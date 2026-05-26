"""CP-side step-up MFA enforcement (RFC 9470 + OIDC ``amr`` / ``auth_time``).

Phase J of the AWS hybrid rollout. Mirrors the AQP-side
:mod:`aqp.api.security_stepup` semantics so destructive ``/manage/*``
routes (Terraform apply/destroy/halt/unlock, future kill-switch
fan-out targets) gate on a *fresh* MFA-bound login the same way the
in-monolith routes do.

Per AGENTS hard rule 52 the step-up boundary MUST NOT be soft-failed
even in permissive auth modes — a permissive bypass on a kill-switch
defeats the entire purpose. This module always raises on failure.

The dep is implemented entirely on standard OIDC claims, identical
to the AQP-side helper so a single ``useStepUp`` hook works for both
surfaces:

- ``amr`` (RFC 8176)
- ``auth_time``
- ``acr`` (Auth0 emits the multi-factor URI when MFA was completed)
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from aqp_cp.auth.deps import AuthenticatedUser, require_auth
from aqp_cp.settings import get_settings

logger = logging.getLogger(__name__)


ACR_MFA: str = "http://schemas.openid.net/pape/policies/2007/06/multi-factor"

MFA_AMR_VALUES: frozenset[str] = frozenset(
    {"mfa", "otp", "hwk", "swk", "face", "fpt", "iris"}
)

DEFAULT_STEP_UP_MAX_AGE_SECONDS: int = 180


def _step_up_enabled() -> bool:
    """Mirrors ``AQP_AUTH_STEP_UP_ENABLED`` — honour the operator-set flag.

    Defaults to True. The CP exposes the same env knob as the monolith
    so flipping it once disables both planes' step-up gates uniformly
    during incident response.
    """
    raw = getattr(get_settings(), "auth_step_up_enabled", True)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() not in {"0", "false", "no", "off"}
    return bool(raw)


def _config_default_max_age() -> int:
    raw = getattr(get_settings(), "auth_step_up_default_max_age", None)
    try:
        value = int(raw) if raw is not None else DEFAULT_STEP_UP_MAX_AGE_SECONDS
        return value if value > 0 else DEFAULT_STEP_UP_MAX_AGE_SECONDS
    except (TypeError, ValueError):
        return DEFAULT_STEP_UP_MAX_AGE_SECONDS


def _coerce_amr(claims: dict[str, Any]) -> frozenset[str]:
    raw = claims.get("amr")
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        return frozenset({raw.strip().lower()}) if raw.strip() else frozenset()
    if isinstance(raw, (list, tuple, set)):
        out: set[str] = set()
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.add(item.strip().lower())
        return frozenset(out)
    return frozenset()


def _coerce_acr(claims: dict[str, Any]) -> str | None:
    raw = claims.get("acr")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _coerce_auth_time(claims: dict[str, Any]) -> int | None:
    raw = claims.get("auth_time")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _has_mfa(claims: dict[str, Any]) -> bool:
    if _coerce_amr(claims) & MFA_AMR_VALUES:
        return True
    if _coerce_acr(claims) == ACR_MFA:
        return True
    return False


def _is_fresh(claims: dict[str, Any], *, max_age_seconds: int) -> bool:
    auth_time = _coerce_auth_time(claims)
    if auth_time is None:
        return False
    age = int(time.time()) - auth_time
    if age < 0:
        # Token from the future — honour issuer clock skew tolerance.
        return age > -60
    return age <= max_age_seconds


def _stepup_www_authenticate(
    *,
    max_age_seconds: int,
    acr_values: str = ACR_MFA,
    error: str = "insufficient_user_authentication",
    error_description: str | None = None,
) -> str:
    """Build an RFC 9470 ``WWW-Authenticate`` header value.

    The SPA + CLI helpers parse it and re-issue the original request
    with a fresh MFA-bound token.
    """
    parts = [f'Bearer error="{error}"']
    if error_description:
        parts.append(f'error_description="{error_description}"')
    if acr_values:
        parts.append(f'acr_values="{acr_values}"')
    parts.append(f'max_age="{int(max_age_seconds)}"')
    return ", ".join(parts)


def require_step_up(
    max_age_seconds: int | None = None,
    *,
    require_mfa_amr: bool = True,
) -> Callable[..., AuthenticatedUser]:
    """Build a dep that requires fresh MFA within ``max_age_seconds``.

    Mirrors :func:`aqp.api.security_stepup.require_step_up`. Apply via
    ``Depends(require_step_up(max_age_seconds=180))`` on every destructive
    ``/manage/*`` route. Local-mode (auth disabled) sees no challenge.
    """
    window = (
        int(max_age_seconds)
        if max_age_seconds is not None
        else _config_default_max_age()
    )

    async def _dep(
        request: Request,
        user: AuthenticatedUser = Depends(require_auth),
    ) -> AuthenticatedUser:
        if not _step_up_enabled() or user.is_anonymous:
            return user
        claims = dict(user.payload or {})
        if not claims:
            logger.warning(
                "step_up denied path=%s user=%s reason=no_claims",
                getattr(request.url, "path", ""),
                user.sub,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "insufficient_user_authentication",
                    "error_description": "fresh re-authentication required",
                },
                headers={
                    "WWW-Authenticate": _stepup_www_authenticate(
                        max_age_seconds=window,
                        error_description="fresh re-authentication required",
                    ),
                },
            )
        if require_mfa_amr and not _has_mfa(claims):
            logger.warning(
                "step_up denied path=%s user=%s reason=missing_mfa_amr amr=%s acr=%s",
                getattr(request.url, "path", ""),
                user.sub,
                sorted(_coerce_amr(claims)),
                _coerce_acr(claims),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "insufficient_user_authentication",
                    "error_description": "fresh MFA required",
                },
                headers={
                    "WWW-Authenticate": _stepup_www_authenticate(
                        max_age_seconds=window,
                        error_description="fresh MFA required",
                    ),
                },
            )
        if not _is_fresh(claims, max_age_seconds=window):
            logger.warning(
                "step_up denied path=%s user=%s reason=stale_auth_time auth_time=%s",
                getattr(request.url, "path", ""),
                user.sub,
                _coerce_auth_time(claims),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "insufficient_user_authentication",
                    "error_description": (
                        f"fresh authentication required (within {window}s; "
                        f"auth_time was {_coerce_auth_time(claims)})"
                    ),
                },
                headers={
                    "WWW-Authenticate": _stepup_www_authenticate(
                        max_age_seconds=window,
                        error_description="fresh authentication required",
                    ),
                },
            )
        return user

    return _dep


__all__ = [
    "ACR_MFA",
    "DEFAULT_STEP_UP_MAX_AGE_SECONDS",
    "MFA_AMR_VALUES",
    "require_step_up",
]
