"""``/_internal/auth0/sync`` — M2M-secured endpoint for Auth0 Actions.

The Auth0 Action invokes this endpoint during the login pipeline
(``onExecutePostLogin``) and uses the response to inject AQP-namespaced
custom claims into the access token before it's signed. See
``docs/auth0-actions.md`` for the Action snippet.

The endpoint is intentionally outside the normal ``/auth/...`` prefix
so the Cloudflare Tunnel / Nginx rewrite rules can keep it on a
separate path that only the Auth0 IPs are allowed to hit (defense in
depth on top of the M2M token requirement).

Authorization: requires an M2M Bearer token whose audience matches
``settings.auth_m2m_audience``. Unauthenticated requests get a 401.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from aqp.auth.oidc import (
    InvalidTokenError,
    JWKSUnavailableError,
    OIDCError,
    get_oidc_config,
    validate_jwt,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/_internal/auth0", tags=["auth0-sync"])


# ---------------------------------------------------------------------------
# M2M token verification dep
# ---------------------------------------------------------------------------


def require_m2m_token(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    """Verify the M2M Bearer token and return its claims.

    The token must:

    - be issued by the same OIDC tenant configured via
      ``AQP_AUTH_OIDC_ISSUER``;
    - carry ``aud=AQP_AUTH_M2M_AUDIENCE`` (defaults to
      ``AQP_AUTH_OIDC_AUDIENCE`` when M2M-specific audience is unset);
    - be signed by the issuer's JWKS.

    Returns the verified claims dict so the route handler can audit
    which Action invoked it.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(None, 1)[1].strip()

    cfg = get_oidc_config()
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not configured",
        )

    try:
        from aqp.config import settings

        m2m_audience = (
            str(getattr(settings, "auth_m2m_audience", "") or "").strip()
            or cfg.audience
        )
    except Exception:
        m2m_audience = cfg.audience

    # Build a per-call config so the M2M audience can differ from the
    # SPA audience (Auth0 best practice).
    from aqp.auth.oidc import OIDCConfig

    m2m_cfg = OIDCConfig(
        issuer=cfg.issuer,
        audience=m2m_audience,
        client_id=cfg.client_id,
        jwks_ttl_seconds=cfg.jwks_ttl_seconds,
        leeway_seconds=cfg.leeway_seconds,
    )

    try:
        return validate_jwt(token, config=m2m_cfg)
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


# ---------------------------------------------------------------------------
# Request / response shapes
# ---------------------------------------------------------------------------


class Auth0SyncRequest(BaseModel):
    """Payload the Auth0 Action sends on every login."""

    user_id: str = Field(
        ..., description="Auth0 user id, e.g. 'auth0|abc' or 'google-oauth2|123'."
    )
    email: str | None = Field(default=None)
    organization_id: str | None = Field(
        default=None,
        description=(
            "Standard Auth0 ``org_id`` claim when the user logged in via "
            "an Auth0 Organization."
        ),
    )
    organization_name: str | None = Field(default=None)
    connection: str | None = Field(
        default=None,
        description=(
            "Optional top-level Auth0 connection name for backward "
            "compatibility. Prefer ``requested_claims.connection``."
        ),
    )
    requested_claims: dict | None = Field(
        default=None,
        description=(
            "Optional hint from the SPA OR the Auth0 Action. Recognised keys: "
            "``workspace_id`` (operator-pinned active workspace), "
            "``connection`` (Auth0 connection name, e.g. 'azure-ad-myorg', "
            "set by the post-login Action so the backend audit log records "
            "which IdP drove this login), ``strategy`` (Auth0 connection "
            "strategy, e.g. 'waad' for Azure AD)."
        ),
    )


class Auth0SyncResponse(BaseModel):
    """Custom claims the Action injects into the access token.

    Every key is namespaced under ``settings.auth_claims_namespace``
    (default ``https://aqp.internal/``) so it can never collide with
    reserved JWT claims. The Action passes this dict directly to
    ``api.accessToken.setCustomClaim`` so the SPA + backend see a
    uniform claim namespace.

    The ``resources`` claim (ADR 003) is the canonical resource-scoping
    grant. Every list endpoint in the control plane filters its results
    through :func:`aqp_platform_core.auth.resource_filter.filter_resources`
    against this claim. The bypass scope is ``admin:cluster``.
    """

    org_id: str | None = None
    team_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    lab_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    resources: list[str] = Field(
        default_factory=list,
        description=(
            "Explicit resource IDs (Deployments, Bots, RL experiments, etc.) "
            "the user is allowed to see. Anyone without admin:cluster will see "
            "ONLY items whose id is in this list."
        ),
    )
    scopes: list[str] = Field(
        default_factory=list,
        description=(
            "Optional RBAC scope grants on top of the roles array. Standard "
            "values: read:infrastructure, manage:agents, manage:infrastructure, "
            "admin:cluster (the only one that bypasses resource filtering)."
        ),
    )
    connection: str | None = None
    internal_user_id: str | None = None
    is_new_user: bool = False


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/sync", response_model=Auth0SyncResponse)
def auth0_sync(
    body: Auth0SyncRequest,
    _claims: dict = Depends(require_m2m_token),
) -> Auth0SyncResponse:
    """Lazy-provision an internal user + return custom claims for the JWT.

    The Auth0 Action invokes this on every login. The response is
    injected into the access token via ``setCustomClaim`` so the
    backend's :func:`aqp.auth.user.provision_user_from_claims` chain
    sees the user's org / team / role on the very first request.
    """
    from aqp.config.defaults import DEFAULT_WORKSPACE_ID, ROLE_VIEWER
    from aqp.persistence.db import get_session
    from aqp.persistence.models_tenancy import Membership, User

    # Phase 4 / ADR 003 — resource scoping. Local default until a richer
    # resolver lands in Phase 7 (rpi_kubernetes absorption); for now we
    # emit an empty list so non-admin users see nothing (deny by default).
    # Operators on aqp-superadmin (admin:cluster) bypass via the scope
    # claim — never via this list.
    def _resolve_resource_ids(user_id: int | None) -> list[str]:
        if user_id is None:
            return []
        try:
            from aqp.auth.resource_scope import (  # type: ignore[import-not-found]
                list_user_resource_ids,
            )

            return list_user_resource_ids(user_id)
        except ImportError:
            # Resource resolver not yet present in this branch — fall
            # through to the empty list. Admins bypass via the scope
            # check; non-admins simply see only what they own once the
            # resolver lands.
            return []
        except Exception:  # noqa: BLE001
            logger.warning(
                "resource id resolution failed for user_id=%s; emitting empty list",
                user_id,
            )
            return []

    def _resolve_scopes(role_list: list[str]) -> list[str]:
        # Map roles to the canonical four-scope grid (ADR 003).
        try:
            from aqp_platform_core.auth.rbac import expand_role

            granted: set[str] = set()
            for role in role_list:
                granted.update(expand_role(role))
            return sorted(granted)
        except Exception:  # noqa: BLE001
            return []

    requested_claims = body.requested_claims if isinstance(body.requested_claims, dict) else {}
    # Convention: the Auth0 post-login Action sends connection metadata via
    # ``requested_claims.connection`` so audit trails capture which IdP
    # drove the login; keep ``body.connection`` as a backward-compatible
    # fallback for older clients.
    connection = requested_claims.get("connection") or body.connection
    if connection is not None and not isinstance(connection, str):
        connection = str(connection)

    is_new = False
    with get_session() as session:
        user_row = (
            session.query(User).filter(User.auth_subject == body.user_id).one_or_none()
        )
        if user_row is None and body.email:
            user_row = (
                session.query(User).filter(User.email == body.email.lower()).one_or_none()
            )

        if user_row is None:
            # The actual user-row creation happens on the first request
            # the SPA makes (provision_user_from_claims). Here we just
            # return the default workspace claim so the Action injects
            # something useful even before the row exists.
            internal_user_id = None
            is_new = True
            org_id = body.organization_id
            workspace_id = DEFAULT_WORKSPACE_ID
            roles: list[str] = [ROLE_VIEWER]
        else:
            internal_user_id = user_row.id
            roles = sorted(
                {
                    m.role
                    for m in (
                        session.query(Membership)
                        .filter(Membership.user_id == user_row.id)
                        .all()
                    )
                }
            )
            ws_membership = (
                session.query(Membership)
                .filter(
                    Membership.user_id == user_row.id,
                    Membership.scope_kind == "workspace",
                )
                .first()
            )
            workspace_id = (
                ws_membership.scope_id if ws_membership else DEFAULT_WORKSPACE_ID
            )
            org_membership = (
                session.query(Membership)
                .filter(
                    Membership.user_id == user_row.id,
                    Membership.scope_kind == "org",
                )
                .first()
            )
            org_id = org_membership.scope_id if org_membership else body.organization_id

    try:
        from aqp.auth.audit import emit_audit_event

        emit_audit_event(
            "auth0_sync",
            user_id=internal_user_id,
            organization_id=body.organization_id,
            event_category="authn",
            source="auth0_action",
            connection=connection,
            details={
                "auth0_user_id": body.user_id,
                "email": body.email,
                "organization_name": body.organization_name,
                "is_new_user": is_new,
            },
        )
    except Exception:
        pass

    resource_ids = _resolve_resource_ids(internal_user_id)
    scopes = _resolve_scopes(roles)

    return Auth0SyncResponse(
        org_id=org_id,
        workspace_id=workspace_id,
        roles=roles,
        resources=resource_ids,
        scopes=scopes,
        connection=connection,
        internal_user_id=internal_user_id,
        is_new_user=is_new,
    )


__all__ = ["router"]
