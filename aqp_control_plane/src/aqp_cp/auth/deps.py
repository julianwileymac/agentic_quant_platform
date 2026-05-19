"""FastAPI dependencies — ``require_auth`` and ``require_scope``.

Mirrors :mod:`aqp.api.security` shape (``CurrentUser`` -> JWT payload)
but ONLY imports from :mod:`aqp_platform_core`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from fastapi import Depends, Header, HTTPException, Request, status

from aqp_platform_core.auth import (
    JwtValidationError,
    SCOPE_ADMIN_CLUSTER,
    extract_claim,
    filter_resources as core_filter_resources,
    has_admin_cluster,
    user_resource_ids,
)

from aqp_cp.auth.validator import get_validator
from aqp_cp.settings import get_settings


@dataclass(slots=True)
class AuthenticatedUser:
    """Resolved request principal — JWT subject + claims + computed scopes."""

    sub: str
    payload: dict[str, Any]
    scopes: frozenset[str]
    org_id: str | None = None
    workspace_id: str | None = None
    roles: tuple[str, ...] = field(default_factory=tuple)
    resources: frozenset[str] = field(default_factory=frozenset)
    is_anonymous: bool = False

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes or SCOPE_ADMIN_CLUSTER in self.scopes


_ANONYMOUS = AuthenticatedUser(
    sub="anonymous",
    payload={},
    scopes=frozenset({SCOPE_ADMIN_CLUSTER}),  # local dev sees everything
    org_id=None,
    workspace_id=None,
    roles=("aqp-superadmin",),
    resources=frozenset(),
    is_anonymous=True,
)


def _extract_scopes(payload: dict[str, Any]) -> frozenset[str]:
    scopes: set[str] = set()
    raw_scope = payload.get("scope")
    if isinstance(raw_scope, str):
        scopes.update(raw_scope.split())
    permissions = payload.get("permissions") or []
    if isinstance(permissions, list):
        scopes.update(str(p) for p in permissions)
    ns_scopes = extract_claim(payload, "scopes", default=None)
    if isinstance(ns_scopes, list):
        scopes.update(str(p) for p in ns_scopes)
    # Roles -> scope expansion via the RBAC lattice.
    ns_roles = extract_claim(payload, "roles", default=None)
    if isinstance(ns_roles, list):
        try:
            from aqp_platform_core.auth.rbac import expand_role

            for role in ns_roles:
                scopes.update(expand_role(str(role)))
        except Exception:  # noqa: BLE001
            pass
    return frozenset(scopes)


def _payload_to_user(payload: dict[str, Any]) -> AuthenticatedUser:
    org_id = extract_claim(payload, "org_id", default=None)
    workspace_id = extract_claim(payload, "workspace_id", default=None)
    roles_raw = extract_claim(payload, "roles", default=()) or ()
    roles = tuple(str(r) for r in roles_raw) if isinstance(roles_raw, (list, tuple)) else ()
    scopes = _extract_scopes(payload)
    return AuthenticatedUser(
        sub=str(payload.get("sub", "")),
        payload=payload,
        scopes=scopes,
        org_id=str(org_id) if org_id else None,
        workspace_id=str(workspace_id) if workspace_id else None,
        roles=roles,
        resources=frozenset(user_resource_ids(payload)),
    )


async def require_auth(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AuthenticatedUser:
    """Validate the bearer JWT and return the resolved user.

    When ``auth_required`` is False (local dev / sandbox), returns a
    synthesised anonymous user with the ``admin:cluster`` scope so the
    dev loop keeps working without an Auth0 tenant.
    """
    settings = get_settings()
    if not settings.auth_enabled:
        return _ANONYMOUS

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_request", "error_description": "Missing Bearer token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(None, 1)[1].strip()

    validator = await get_validator()
    if validator is None:
        # Mis-config: auth_required=true but no issuer configured.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "auth_unconfigured", "error_description": "OIDC issuer not set"},
        )

    try:
        payload = await validator.validate(token)
    except JwtValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": exc.code, "error_description": str(exc)},
            headers={"WWW-Authenticate": f'Bearer error="{exc.code}"'},
        ) from exc

    user = _payload_to_user(payload)
    # Stash on request.state so downstream handlers + filter_resources_for_user
    # can read the verified payload without re-validating.
    request.state.aqp_user = user
    request.state.aqp_jwt_payload = payload
    return user


def require_scope(*required_scopes: str) -> Callable[..., AuthenticatedUser]:
    """Build a dep that asserts every scope in ``required_scopes`` is granted.

    Bypassed for ``admin:cluster``. Returns 403 with a structured body
    when a scope is missing.
    """
    required = tuple(required_scopes)

    async def _dep(user: AuthenticatedUser = Depends(require_auth)) -> AuthenticatedUser:
        if user.has_scope(SCOPE_ADMIN_CLUSTER):
            return user
        missing = [s for s in required if s not in user.scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "insufficient_scope",
                    "error_description": f"missing scope(s): {missing}",
                    "required": list(required),
                    "granted": sorted(user.scopes),
                },
            )
        return user

    return _dep


def filter_resources_for_user(
    items: list,
    user: AuthenticatedUser,
    *,
    id_getter: Callable[[Any], str | None] | None = None,
) -> list:
    """Apply resource-scoped filtering using the authenticated user's claims.

    Calls into :func:`aqp_platform_core.auth.filter_resources` with the
    user's JWT payload. Returns the unfiltered list for anonymous /
    local-dev users (admin:cluster bypass already applies).
    """
    if user.is_anonymous or user.has_scope(SCOPE_ADMIN_CLUSTER):
        return list(items)
    return core_filter_resources(items, user.payload, id_getter=id_getter)


__all__ = [
    "AuthenticatedUser",
    "filter_resources_for_user",
    "has_admin_cluster",
    "require_auth",
    "require_scope",
]
