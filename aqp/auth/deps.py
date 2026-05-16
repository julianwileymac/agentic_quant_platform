"""FastAPI dependencies — the request-scoped seam for tenancy.

Use these in every new route, and migrate existing routes incrementally:

.. code-block:: python

    from fastapi import Depends
    from aqp.auth import current_context, require_workspace
    from aqp.auth.context import RequestContext

    @router.get("/strategies")
    def list_strategies(
        ctx: RequestContext = Depends(current_context),
        ws_id: str = Depends(require_workspace),
    ):
        ...

The deps respect three optional headers:

- ``X-AQP-User`` — bypass identity resolution for service-to-service calls
  (only honoured when ``settings.auth_provider == "local"``).
- ``X-AQP-Workspace`` — pin the active workspace.
- ``X-AQP-Project`` / ``X-AQP-Lab`` — pin the active project / lab.

In OIDC mode the user is resolved from the standard
``Authorization: Bearer <jwt>`` header instead of ``X-AQP-User``. The
JWT is verified against the issuer's JWKS (see :mod:`aqp.auth.oidc`)
and the ``sub`` claim is mapped onto a :class:`User` row, lazily
provisioning a new row + default :class:`Membership` on first contact.

Without an Authorization header the local-first default user is used —
this preserves the workflow for CLIs, Celery workers, and unit tests.
"""
from __future__ import annotations

import logging
from typing import Callable

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from aqp.auth.context import RequestContext, default_context, scope_id_for
from aqp.auth.contextvars import bind_context
from aqp.auth.oidc import (
    InvalidTokenError,
    JWKSUnavailableError,
    OIDCError,
    claims_subject,
    get_oidc_config,
    validate_jwt,
)
from aqp.auth.user import (
    CurrentUser,
    accessible_labs,
    accessible_projects,
    accessible_workspaces,
    default_user,
    resolve_user,
    user_can,
)
from aqp.config.defaults import (
    DEFAULT_ORG_ID,
    SCOPE_LAB,
    SCOPE_ORG,
    SCOPE_PROJECT,
    SCOPE_TEAM,
    SCOPE_WORKSPACE,
)

logger = logging.getLogger(__name__)


# Tokens are optional at the dep layer — local-first deployments keep
# working without an Authorization header. Routes that strictly require
# auth should depend on :func:`require_authenticated`.
_bearer_scheme = HTTPBearer(auto_error=False)


def _token_from_session_cookie(request: Request) -> str | None:
    """Pull a verified-style access_token out of the ``aqp_session`` cookie.

    The backend-session login flow in :mod:`aqp.api.routes.auth` mints a
    JWE-encrypted ``aqp_session`` cookie carrying the IdP-issued access
    token. This helper decrypts it (using the same secret used to mint
    it) and returns the access_token so the standard JWT path below
    can validate it. Returns ``None`` for any failure (missing cookie,
    bad secret, decrypt error, missing token) — the caller falls back
    to the default user, matching the bearer-less branch.
    """
    try:
        from aqp.config import settings
    except Exception:
        return None
    secret = str(getattr(settings, "auth_session_secret", "") or "")
    if not secret:
        return None
    cookie_name = str(getattr(settings, "auth_session_cookie", "aqp_session") or "aqp_session")
    token = request.cookies.get(cookie_name)
    if not token:
        return None
    try:
        from aqp.auth.session import EncryptedCookieStateStore
    except Exception:
        return None
    try:
        store = EncryptedCookieStateStore(secret=secret, cookie_name=cookie_name)
        # /auth/callback uses the cookie name as the HKDF salt (see
        # aqp.api.routes.auth.login_callback); the same identifier
        # must be passed to .get() so HKDF derives the matching key.
        payload = store.get(cookie_name, token=token)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    # session_payload_from_tokens() produces ``token_sets`` with one
    # entry per audience. We accept the first non-empty access_token —
    # the backend-session flow only writes one entry today.
    sets = payload.get("token_sets")
    if isinstance(sets, list):
        for entry in sets:
            if isinstance(entry, dict):
                tok = entry.get("access_token")
                if isinstance(tok, str) and tok:
                    return tok
    # Some legacy payloads carried the access token at the top level.
    legacy = payload.get("access_token")
    return legacy if isinstance(legacy, str) and legacy else None


def current_user(
    request: Request,
    x_aqp_user: str | None = Header(default=None, alias="X-AQP-User"),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    """Resolve the current user.

    OIDC mode (``settings.auth_provider != "local"``):
        Validate the ``Authorization: Bearer`` JWT against the configured
        issuer / audience. Map the verified ``sub`` claim onto a ``User``
        row, lazily provisioning one (with a default workspace
        ``Membership``) on first login. When no Bearer header is
        present, fall back to the encrypted ``aqp_session`` cookie set
        by :http:get:`/auth/callback` — same JWT validation path, just
        sourced from a server-side session.

    Local mode:
        Fall back to the deterministic default user, optionally honoring
        the ``X-AQP-User`` header for service-to-service calls.

    Failure modes:
        ``HTTPException(401)`` for malformed / expired / wrong-audience
        tokens, ``HTTPException(503)`` if the JWKS endpoint is
        unreachable and no cached document exists, and graceful fall-
        back to the default user when no header is supplied.
    """
    try:
        from aqp.config import settings

        provider = str(settings.auth_provider).lower()
    except Exception:
        provider = "local"

    if provider != "local":
        bearer_token: str | None = (
            credentials.credentials if credentials is not None else None
        )
        if not bearer_token:
            # Fall back to the encrypted session cookie minted by
            # /auth/callback. Closes the documented Bearer-only gap so
            # SSR pages + browsers that don't attach Authorization
            # still reach the resolved identity.
            bearer_token = _token_from_session_cookie(request)
        if not bearer_token:
            # No Authorization header supplied; surface the local default
            # so unauthenticated reads (e.g. health probes) keep working.
            # Routes that strictly require auth chain ``require_authenticated``.
            return default_user()

        oidc_config = get_oidc_config()
        if oidc_config is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "OIDC is enabled (auth_provider=%s) but issuer/audience are "
                    "not configured. Set AQP_AUTH_OIDC_ISSUER + "
                    "AQP_AUTH_OIDC_AUDIENCE." % provider
                ),
            )
        try:
            claims = validate_jwt(bearer_token, config=oidc_config)
        except InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            ) from exc
        except JWKSUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except OIDCError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc

        # Cache claims on the request so downstream deps / routes can
        # surface profile fields without re-decoding the token.
        request.state.oidc_claims = claims

        try:
            sub = claims_subject(claims)
        except InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            ) from exc
        return resolve_user(
            auth_subject=sub,
            email=claims.get("email"),
            claims=claims,
            auto_provision=True,
            fallback_to_default=False,
        )

    if x_aqp_user:
        return resolve_user(user_id=x_aqp_user, fallback_to_default=True)
    return default_user()


def require_authenticated(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """Dep that returns the current user, refusing the local-default.

    Use on routes that must NOT be reachable by unauthenticated clients
    in OIDC deployments (e.g. the ``/datasets/upload`` multipart sink,
    ``/auth/exchange``, anything that mutates state across tenants).
    Local-first developer setups are unaffected because the default
    user is allowed when ``settings.auth_provider == "local"``.
    """
    try:
        from aqp.config import settings

        provider = str(settings.auth_provider).lower()
    except Exception:
        provider = "local"

    if provider != "local" and user.is_default:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _first_scope_membership(user: CurrentUser, scope_kind: str) -> str | None:
    for membership in user.memberships:
        if membership.get("scope_kind") != scope_kind:
            continue
        scope_id = membership.get("scope_id")
        if isinstance(scope_id, str) and scope_id:
            return scope_id
    return None


def _org_for_workspace(workspace_id: str | None) -> str | None:
    if not workspace_id:
        return None
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import Workspace

        with get_session() as session:
            row = (
                session.query(Workspace.org_id)
                .filter(Workspace.id == workspace_id)
                .one_or_none()
            )
            if row is None:
                return None
            return str(row[0]) if row[0] else None
    except Exception:
        logger.debug("Could not derive org_id from workspace_id=%s", workspace_id, exc_info=True)
        return None


def current_context(
    user: CurrentUser = Depends(current_user),
    x_aqp_workspace: str | None = Header(default=None, alias="X-AQP-Workspace"),
    x_aqp_project: str | None = Header(default=None, alias="X-AQP-Project"),
    x_aqp_lab: str | None = Header(default=None, alias="X-AQP-Lab"),
    x_aqp_org: str | None = Header(default=None, alias="X-AQP-Org"),
    x_aqp_team: str | None = Header(default=None, alias="X-AQP-Team"),
) -> RequestContext:
    """Build a :class:`RequestContext` from the resolved user + headers.

    Validates that the user can access the requested workspace/project/lab.
    Falls back to the user's home context when no headers are provided.

    The ``X-AQP-Org`` / ``X-AQP-Team`` headers were added in Phase 6 of
    the multi-tenant rollout so the frontend's ContextBar can pin a
    specific org / team. They follow the same membership-check rules
    as the workspace / project / lab headers.
    """
    if user.is_default:
        ctx = default_context()
    else:
        ws_ids = accessible_workspaces(user)
        project_ids = accessible_projects(user)
        lab_ids = accessible_labs(user)
        workspace_id = ws_ids[0] if ws_ids else None
        org_id = (
            _first_scope_membership(user, SCOPE_ORG)
            or _org_for_workspace(workspace_id)
            or DEFAULT_ORG_ID
        )
        ctx = RequestContext(
            user_id=user.id,
            org_id=org_id,
            team_id=_first_scope_membership(user, SCOPE_TEAM),
            workspace_id=workspace_id,
            project_id=project_ids[0] if project_ids else None,
            lab_id=lab_ids[0] if lab_ids else None,
        )

    overrides: dict[str, object] = {}
    if x_aqp_workspace:
        if not user.is_default and not user_can(
            user, "viewer", scope_kind=SCOPE_WORKSPACE, scope_id=x_aqp_workspace
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not a member of workspace {x_aqp_workspace}",
            )
        overrides["workspace_id"] = x_aqp_workspace
        overrides["project_id"] = None
        overrides["lab_id"] = None

    if x_aqp_project:
        if not user.is_default and not user_can(
            user, "viewer", scope_kind=SCOPE_PROJECT, scope_id=x_aqp_project
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cannot access project {x_aqp_project}",
            )
        overrides["project_id"] = x_aqp_project

    if x_aqp_lab:
        if not user.is_default and not user_can(
            user, "viewer", scope_kind=SCOPE_LAB, scope_id=x_aqp_lab
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cannot access lab {x_aqp_lab}",
            )
        overrides["lab_id"] = x_aqp_lab

    if x_aqp_org:
        if not user.is_default and not user_can(
            user, "viewer", scope_kind=SCOPE_ORG, scope_id=x_aqp_org
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not a member of org {x_aqp_org}",
            )
        overrides["org_id"] = x_aqp_org

    if x_aqp_team:
        if not user.is_default and not user_can(
            user, "viewer", scope_kind=SCOPE_TEAM, scope_id=x_aqp_team
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not a member of team {x_aqp_team}",
            )
        overrides["team_id"] = x_aqp_team

    resolved = ctx.with_overrides(**overrides) if overrides else ctx
    # Bind the active context onto the request-scoped ContextVar so deep
    # chokepoints (Iceberg writer, MCP bridge, ledger writer, agent
    # runtime) can re-hydrate ``RequestContext`` without threading it
    # through every signature. Reset happens automatically when the
    # request task ends.
    bind_context(resolved)
    return resolved


# ---------------------------------------------------------------------------
# Convenience dependencies for "this route requires X" guards
# ---------------------------------------------------------------------------
def require_workspace(ctx: RequestContext = Depends(current_context)) -> str:
    """Dep that returns the active workspace id, raising 400 if missing."""
    if not ctx.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active workspace required (set X-AQP-Workspace header)",
        )
    return ctx.workspace_id


def require_project(ctx: RequestContext = Depends(current_context)) -> str:
    if not ctx.project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active project required (set X-AQP-Project header)",
        )
    return ctx.project_id


def require_lab(ctx: RequestContext = Depends(current_context)) -> str:
    if not ctx.lab_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active lab required (set X-AQP-Lab header)",
        )
    return ctx.lab_id


def require_role(role: str, scope_kind: str) -> Callable[..., RequestContext]:
    """Build a dep that asserts the current user satisfies *role* on the scope.

    Usage:

    .. code-block:: python

        @router.delete("/workspaces/{wid}")
        def delete_workspace(
            wid: str,
            _: RequestContext = Depends(require_role("admin", "workspace")),
        ):
            ...
    """

    def dep(
        user: CurrentUser = Depends(current_user),
        ctx: RequestContext = Depends(current_context),
    ) -> RequestContext:
        scope_id = scope_id_for(ctx, scope_kind)
        if scope_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Active {scope_kind} required for this operation",
            )
        if not user_can(user, role, scope_kind=scope_kind, scope_id=scope_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {role!r} required on {scope_kind} {scope_id}",
            )
        return ctx

    return dep


__all__ = [
    "current_context",
    "current_user",
    "require_authenticated",
    "require_lab",
    "require_project",
    "require_role",
    "require_workspace",
]
