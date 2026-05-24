"""Step-up MFA enforcement primitives (RFC 9470, OIDC ``acr_values`` + ``max_age``).

This module provides the per-route escalation point for destructive or
otherwise high-risk operations (kill-switch, all ``/halt`` fan-out
targets, BYOK / OAuth credential deletes, Terraform apply / destroy,
organization invite issuance, broker-credential mutations, and the
admin tenancy-strategy migration). The plain
:func:`aqp.api.security.require_authenticated` /
:func:`require_scope` chain validates that a token was issued for the
right user with the right RBAC permissions; this module is the
additional gate that demands a *fresh* MFA-authenticated session.

The contract is implemented entirely on top of standard OIDC claims:

- ``amr`` (Authentication Method References, RFC 8176): the list of
  authentication methods used at login (e.g. ``["pwd", "mfa", "otp"]``).
- ``auth_time``: the Unix timestamp of the *most recent* authentication
  event. Refresh tokens preserve ``auth_time``; only an interactive
  re-authentication updates it.
- ``acr`` (Authentication Context Class Reference): the policy URI
  satisfied by the login. Auth0 emits
  ``http://schemas.openid.net/pape/policies/2007/06/multi-factor`` when
  MFA was completed.

When a request fails the check, the response carries an RFC 9470
``WWW-Authenticate: Bearer error="insufficient_user_authentication"``
header with the ``max_age`` and ``acr_values`` the client must request
on the next ``getAccessTokenSilently`` / ``loginWithRedirect`` call.
The SPA + CLI helpers ``useStepUp`` / ``ensure_step_up`` honour the
header and re-issue the original request transparently.

Step-up enforcement is the boundary that **MUST NOT** be soft-failed
even in ``AQP_AUTH_ENFORCE=permissive`` mode — a permissive bypass on a
kill-switch defeats the entire purpose. We therefore raise
:class:`HTTPException` directly instead of routing through
:func:`aqp.api.security._violation`.

See AGENTS.md hard rule 52 and the canonical
``aqp_docs/auth0-setup.md`` Phase 1 walkthrough.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from aqp.api.security import require_authenticated
from aqp.auth import CurrentUser, RequestContext, current_context
from aqp.auth.audit import emit_audit_event
from aqp.config import settings

logger = logging.getLogger(__name__)


# RFC-defined ACR values + AMR tags
ACR_MFA: str = "http://schemas.openid.net/pape/policies/2007/06/multi-factor"
"""OIDC `acr` value indicating MFA was completed during the most recent login."""

AMR_MFA: str = "mfa"
"""RFC 8176 AMR tag for "multi-factor authentication used"."""

AMR_OTP: str = "otp"
"""RFC 8176 AMR tag for one-time-password (TOTP / SMS code)."""

AMR_HARDWARE: str = "hwk"
"""RFC 8176 AMR tag for hardware key (FIDO2 / WebAuthn / YubiKey)."""

AMR_SOFTWARE_KEY: str = "swk"
"""RFC 8176 AMR tag for software key (proof-of-possession via key)."""

# Any one of these AMR values in the token satisfies the MFA requirement.
# Auth0 emits ``mfa`` for any of: TOTP, SMS, push, WebAuthn, biometric.
# Some IdPs (Entra ID) emit the more specific tag instead of ``mfa``.
MFA_AMR_VALUES: frozenset[str] = frozenset(
    {AMR_MFA, AMR_OTP, AMR_HARDWARE, AMR_SOFTWARE_KEY, "face", "fpt", "iris"}
)


# ---------------------------------------------------------------------------
# Defaults — sized for the AQP threat model
# ---------------------------------------------------------------------------

DEFAULT_STEP_UP_MAX_AGE_SECONDS: int = 180
"""Default freshness window. Three minutes is short enough to make stolen
session tokens useless against a destructive op, long enough that an
operator who *just* MFA'd to open the dashboard doesn't get prompted
again on every halt button click. Tune via
``AQP_AUTH_STEP_UP_DEFAULT_MAX_AGE`` (see :mod:`aqp.config.settings`)."""


def _config_default_max_age() -> int:
    """Settings-overridable default freshness window."""
    raw = getattr(settings, "auth_step_up_default_max_age", None)
    try:
        if raw is None:
            return DEFAULT_STEP_UP_MAX_AGE_SECONDS
        value = int(raw)
        if value <= 0:
            return DEFAULT_STEP_UP_MAX_AGE_SECONDS
        return value
    except (TypeError, ValueError):
        return DEFAULT_STEP_UP_MAX_AGE_SECONDS


def _step_up_enabled() -> bool:
    """Honour an emergency disable flag for incident response.

    Defaults to ``True``. Setting
    ``AQP_AUTH_STEP_UP_ENABLED=false`` flips every step-up gate into a
    log-only check. The local-default user is always exempt because
    no MFA is possible without an external IdP.
    """
    raw = getattr(settings, "auth_step_up_enabled", True)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() not in {"0", "false", "no", "off"}
    return bool(raw)


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------


def _request_claims(request: Request) -> dict[str, Any] | None:
    """Return the verified OIDC claims stashed by :func:`aqp.auth.deps.current_user`.

    Returns ``None`` for local-default mode (no Bearer token was supplied),
    in which case the calling dep treats the request as locally-trusted
    and skips the check.
    """
    claims = getattr(request.state, "oidc_claims", None)
    if isinstance(claims, dict):
        return claims
    return None


def _coerce_amr(claims: dict[str, Any]) -> frozenset[str]:
    """Return the normalized AMR set from a claims dict.

    Tolerates both the standard list form (``"amr": ["pwd", "mfa"]``)
    and the rare scalar-string form some IdPs emit
    (``"amr": "mfa"``). Always returns lower-cased strings.
    """
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
    """Return ``auth_time`` as an int Unix timestamp, or ``None``."""
    raw = claims.get("auth_time")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _has_mfa(claims: dict[str, Any]) -> bool:
    """True iff the token proves an MFA factor was completed at login."""
    amr = _coerce_amr(claims)
    if amr & MFA_AMR_VALUES:
        return True
    acr = _coerce_acr(claims)
    if acr and acr == ACR_MFA:
        return True
    return False


def _is_fresh(claims: dict[str, Any], *, max_age_seconds: int) -> bool:
    """True iff the most recent authentication is within *max_age_seconds*."""
    auth_time = _coerce_auth_time(claims)
    if auth_time is None:
        return False
    age = int(time.time()) - auth_time
    if age < 0:
        # Token from the future (clock skew); honour the issuer's tolerance.
        return age > -60
    return age <= max_age_seconds


# ---------------------------------------------------------------------------
# Public principal accessor (re-exported for callers that want the raw view)
# ---------------------------------------------------------------------------


def principal_amr(request: Request) -> frozenset[str]:
    """Return the AMR set on the active request, or empty for unauthenticated."""
    claims = _request_claims(request)
    return _coerce_amr(claims) if claims else frozenset()


def principal_auth_time(request: Request) -> int | None:
    """Return the ``auth_time`` Unix timestamp on the active request."""
    claims = _request_claims(request)
    return _coerce_auth_time(claims) if claims else None


def principal_acr(request: Request) -> str | None:
    """Return the ``acr`` claim on the active request."""
    claims = _request_claims(request)
    return _coerce_acr(claims) if claims else None


# ---------------------------------------------------------------------------
# 401 builders — RFC 9470 compliant
# ---------------------------------------------------------------------------


def _stepup_www_authenticate(
    *,
    max_age_seconds: int,
    acr_values: str = ACR_MFA,
    error: str = "insufficient_user_authentication",
    error_description: str | None = None,
) -> str:
    """Build an RFC 9470-compliant ``WWW-Authenticate`` header value.

    Example output::

        Bearer error="insufficient_user_authentication", \
            error_description="fresh mfa required", \
            acr_values="http://schemas.openid.net/pape/policies/2007/06/multi-factor", \
            max_age="180"

    The SPA / CLI helpers parse this and reissue the original request
    after the client has obtained a fresh MFA-bound token.
    """
    parts = [f'Bearer error="{error}"']
    if error_description:
        parts.append(f'error_description="{error_description}"')
    if acr_values:
        parts.append(f'acr_values="{acr_values}"')
    parts.append(f'max_age="{int(max_age_seconds)}"')
    return ", ".join(parts)


def _deny(
    *,
    code: int,
    detail: str,
    max_age_seconds: int,
    request: Request,
    user: CurrentUser | None,
    ctx: RequestContext | None,
    reason: str,
) -> None:
    """Raise an RFC 9470 HTTP error AND emit an audit event.

    Step-up violations are always audit-worthy because they signal that
    a sensitive operation was attempted without sufficient
    authentication. Soft-fail in permissive mode is **explicitly
    forbidden** for step-up gates; this helper raises unconditionally.
    """
    try:
        emit_audit_event(
            "step_up_denied",
            user_id=user.id if user else None,
            organization_id=getattr(ctx, "org_id", None) if ctx else None,
            workspace_id=getattr(ctx, "workspace_id", None) if ctx else None,
            actor_user_id=user.id if user else None,
            event_category="authz",
            severity="warning",
            source="api",
            request=request,
            details={
                "reason": reason,
                "max_age_seconds": max_age_seconds,
                "path": str(getattr(request, "url", "") or ""),
                "method": request.method if request else None,
            },
        )
    except Exception:  # pragma: no cover - audit is best-effort
        logger.debug("step_up audit emit failed", exc_info=True)
    raise HTTPException(
        status_code=code,
        detail=detail,
        headers={
            "WWW-Authenticate": _stepup_www_authenticate(
                max_age_seconds=max_age_seconds,
                error_description=detail,
            ),
        },
    )


# ---------------------------------------------------------------------------
# Public deps
# ---------------------------------------------------------------------------


def require_mfa() -> Callable[..., CurrentUser]:
    """Build a dep that requires the token to prove MFA was completed at login.

    Does **not** check freshness — only that the user successfully
    completed an MFA factor (TOTP / SMS / push / WebAuthn / biometric)
    during the most recent interactive login. Use this for endpoints
    where MFA-ever is required but the operation is not time-sensitive
    (e.g. account self-service that allows long-lived sessions).

    For destructive operations that need fresh MFA, use
    :func:`require_step_up` instead.

    Example::

        @router.post("/me/security/mfa/factors")
        async def add_factor(
            ...,
            user: CurrentUser = Depends(require_mfa()),
        ): ...
    """

    def _dep(
        request: Request,
        user: CurrentUser = Depends(require_authenticated),
        ctx: RequestContext = Depends(current_context),
    ) -> CurrentUser:
        if not _step_up_enabled() or user.is_default:
            return user
        claims = _request_claims(request)
        if claims is None:
            # Authenticated but no OIDC claims (e.g. X-AQP-User header on a
            # local-mode deployment that somehow reached this path). Treat
            # as missing MFA proof — the safer default.
            _deny(
                code=status.HTTP_401_UNAUTHORIZED,
                detail="MFA required for this operation",
                max_age_seconds=_config_default_max_age(),
                request=request,
                user=user,
                ctx=ctx,
                reason="no_oidc_claims",
            )
        if not _has_mfa(claims):
            _deny(
                code=status.HTTP_401_UNAUTHORIZED,
                detail="MFA required for this operation",
                max_age_seconds=_config_default_max_age(),
                request=request,
                user=user,
                ctx=ctx,
                reason="missing_mfa_amr",
            )
        return user

    return _dep


def require_step_up(
    max_age_seconds: int | None = None,
    *,
    require_mfa_amr: bool = True,
) -> Callable[..., CurrentUser]:
    """Build a dep that requires **fresh MFA** within *max_age_seconds*.

    The default freshness window is :data:`DEFAULT_STEP_UP_MAX_AGE_SECONDS`
    (180s), tunable globally via the ``AQP_AUTH_STEP_UP_DEFAULT_MAX_AGE``
    setting. Per-route overrides win:

    .. code-block:: python

        @router.post(
            "/kill_switch",
            dependencies=[Depends(require_step_up(max_age_seconds=120))],
        )
        def kill_switch(...): ...

    The dep raises a 401 with an RFC 9470 ``WWW-Authenticate`` header
    indicating both the required ``acr_values`` and the ``max_age`` the
    client must request on its next token grab. The frontend
    ``useStepUp`` hook parses this and calls
    ``getAccessTokenSilently({ authorizationParams: { acr_values, max_age: 0 } })``
    transparently before retrying the original request.

    ``require_mfa_amr=False`` allows callers that want fresh
    re-authentication without strictly requiring MFA (rare; only used
    for the admin "verify identity" wizard during MFA enrollment
    bootstrapping).

    Local-mode developer setups are exempt: the local default user
    cannot complete MFA, so step-up always passes. Production deploys
    keep ``AQP_AUTH_PROVIDER`` set to a real IdP so the default user
    cannot exist.
    """
    window = int(max_age_seconds) if max_age_seconds is not None else _config_default_max_age()

    def _dep(
        request: Request,
        user: CurrentUser = Depends(require_authenticated),
        ctx: RequestContext = Depends(current_context),
    ) -> CurrentUser:
        if not _step_up_enabled() or user.is_default:
            return user
        claims = _request_claims(request)
        if claims is None:
            _deny(
                code=status.HTTP_401_UNAUTHORIZED,
                detail="fresh re-authentication required",
                max_age_seconds=window,
                request=request,
                user=user,
                ctx=ctx,
                reason="no_oidc_claims",
            )
        if require_mfa_amr and not _has_mfa(claims):
            _deny(
                code=status.HTTP_401_UNAUTHORIZED,
                detail="fresh MFA required",
                max_age_seconds=window,
                request=request,
                user=user,
                ctx=ctx,
                reason="missing_mfa_amr",
            )
        if not _is_fresh(claims, max_age_seconds=window):
            _deny(
                code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    f"fresh authentication required (within {window}s; "
                    f"auth_time was {_coerce_auth_time(claims)})"
                ),
                max_age_seconds=window,
                request=request,
                user=user,
                ctx=ctx,
                reason="stale_auth_time",
            )
        return user

    return _dep


# ---------------------------------------------------------------------------
# Diagnostics — surface step-up state without mutating it
# ---------------------------------------------------------------------------


def step_up_state(request: Request) -> dict[str, Any]:
    """Return a JSON-safe view of the active step-up state.

    Used by ``GET /me/security/step-up`` and the frontend's
    ``useStepUp`` hook so the UI can pre-show whether a sensitive
    button needs a re-auth dialog before the user clicks it.
    """
    claims = _request_claims(request) or {}
    now = int(time.time())
    auth_time = _coerce_auth_time(claims)
    age = (now - auth_time) if auth_time is not None else None
    window = _config_default_max_age()
    return {
        "enabled": _step_up_enabled(),
        "has_mfa": _has_mfa(claims),
        "amr": sorted(_coerce_amr(claims)),
        "acr": _coerce_acr(claims),
        "auth_time": auth_time,
        "age_seconds": age,
        "default_max_age_seconds": window,
        "fresh_within_default_window": _is_fresh(claims, max_age_seconds=window),
    }


__all__ = [
    "ACR_MFA",
    "AMR_MFA",
    "AMR_OTP",
    "AMR_HARDWARE",
    "AMR_SOFTWARE_KEY",
    "DEFAULT_STEP_UP_MAX_AGE_SECONDS",
    "MFA_AMR_VALUES",
    "principal_acr",
    "principal_amr",
    "principal_auth_time",
    "require_mfa",
    "require_step_up",
    "step_up_state",
]
