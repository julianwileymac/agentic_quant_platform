"""Identity dependencies — Entra-primary bearer validation for ``/admin/*``.

Mirrors :mod:`aqp_cp.auth.deps` so the admin BFF carries the same
``AuthenticatedUser`` shape (scopes, roles, resources) into every
route + audit row. Local-dev sandboxes (``AQP_ADMIN_AUTH_REQUIRED=false``)
short-circuit to a synthesised anonymous user with ``admin:cluster``
so contributors can iterate without standing up a full Entra app
registration.

The validator is built once per process and reused. Tests can call
:func:`reset_admin_validator` between cases.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable

from fastapi import Depends, Header, HTTPException, Request, status

from aqp_platform_core.auth import (
    JwtValidationError,
    JwtValidator,
    JwtValidatorConfig,
    SCOPE_ADMIN_CLUSTER,
    extract_claim,
    filter_resources as core_filter_resources,
    msal_entra_jwt_validator_config,
    user_resource_ids,
)

from aqp_admin.settings import AdminSettings, get_settings

_VALIDATOR: JwtValidator | None = None
_VALIDATOR_LOCK = asyncio.Lock()


@dataclass(slots=True)
class AdminUser:
    """Resolved admin principal — JWT subject + claims + computed scopes."""

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


_ANONYMOUS = AdminUser(
    sub="anonymous",
    payload={},
    scopes=frozenset({SCOPE_ADMIN_CLUSTER}),
    is_anonymous=True,
)


def _validator_config(settings: AdminSettings) -> JwtValidatorConfig:
    """Derive the active validator config from the admin settings.

    Entra-primary: when no explicit issuer is set, build the v2.0
    URLs from ``auth_entra_tenant``. Otherwise honour the explicit
    OIDC issuer (e.g. an Auth0 tenant for B2C fallback).
    """
    namespaces = tuple(
        ns for ns in (
            settings.auth_claims_namespace,
            *(settings.auth_claims_namespace_aliases or ()),
        )
        if ns
    )
    if settings.auth_oidc_issuer:
        return JwtValidatorConfig(
            issuer=settings.auth_oidc_issuer,
            audience=settings.auth_oidc_audience,
            leeway_seconds=settings.auth_leeway_seconds,
            jwks_ttl_seconds=settings.auth_jwks_ttl_seconds,
            expected_claim_namespaces=namespaces,
        )
    return msal_entra_jwt_validator_config(
        tenant=settings.auth_entra_tenant,
        audience=settings.auth_oidc_audience,
        leeway_seconds=settings.auth_leeway_seconds,
        jwks_ttl_seconds=settings.auth_jwks_ttl_seconds,
        expected_claim_namespaces=namespaces,
    )


async def _ensure_validator() -> JwtValidator | None:
    global _VALIDATOR
    settings = get_settings()
    if not settings.auth_enabled:
        return None
    if _VALIDATOR is not None:
        return _VALIDATOR
    async with _VALIDATOR_LOCK:
        if _VALIDATOR is None:
            _VALIDATOR = JwtValidator(_validator_config(settings))
    return _VALIDATOR


async def reset_admin_validator() -> None:
    """Drop the validator singleton (test helper + lifespan shutdown)."""
    global _VALIDATOR
    async with _VALIDATOR_LOCK:
        if _VALIDATOR is not None:
            try:
                await _VALIDATOR.close()
            except Exception:  # noqa: BLE001
                pass
            _VALIDATOR = None


def _extract_scopes(payload: dict[str, Any]) -> frozenset[str]:
    scopes: set[str] = set()
    raw_scope = payload.get("scope") or payload.get("scp")  # Entra uses 'scp'
    if isinstance(raw_scope, str):
        scopes.update(raw_scope.split())
    permissions = payload.get("permissions") or []
    if isinstance(permissions, list):
        scopes.update(str(p) for p in permissions)
    ns_scopes = extract_claim(payload, "scopes", default=None)
    if isinstance(ns_scopes, list):
        scopes.update(str(p) for p in ns_scopes)
    ns_roles = extract_claim(payload, "roles", default=None)
    if isinstance(ns_roles, list):
        try:
            from aqp_platform_core.auth.rbac import expand_role

            for role in ns_roles:
                scopes.update(expand_role(str(role)))
        except Exception:  # noqa: BLE001
            pass
    # Entra App Roles surface in the top-level 'roles' claim too.
    top_roles = payload.get("roles")
    if isinstance(top_roles, list):
        try:
            from aqp_platform_core.auth.rbac import expand_role

            for role in top_roles:
                scopes.update(expand_role(str(role)))
        except Exception:  # noqa: BLE001
            pass
    return frozenset(scopes)


def _payload_to_admin(payload: dict[str, Any]) -> AdminUser:
    org_id = extract_claim(payload, "org_id", default=None)
    workspace_id = extract_claim(payload, "workspace_id", default=None)
    roles_raw = extract_claim(payload, "roles", default=()) or ()
    roles = tuple(str(r) for r in roles_raw) if isinstance(roles_raw, (list, tuple)) else ()
    scopes = _extract_scopes(payload)
    # Entra issues 'oid' (object id) as the canonical user identifier
    # alongside 'sub'. Prefer 'oid' when present so audit rows stay
    # consistent across token issuance generations.
    subject = str(payload.get("oid") or payload.get("sub") or "")
    return AdminUser(
        sub=subject,
        payload=payload,
        scopes=scopes,
        org_id=str(org_id) if org_id else None,
        workspace_id=str(workspace_id) if workspace_id else None,
        roles=roles,
        resources=frozenset(user_resource_ids(payload)),
    )


async def require_admin(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AdminUser:
    """Validate the bearer JWT and return the resolved admin user.

    When ``auth_required`` is False (local dev / sandbox), returns a
    synthesised anonymous user with ``admin:cluster`` so the dev loop
    keeps working without an Entra / Auth0 tenant.
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

    validator = await _ensure_validator()
    if validator is None:
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

    user = _payload_to_admin(payload)
    request.state.aqp_admin_user = user
    request.state.aqp_admin_jwt_payload = payload
    return user


def require_admin_scope(*required: str) -> Callable[..., AdminUser]:
    """Build a dep that asserts every scope in ``required`` is granted.

    ``admin:cluster`` short-circuits the check (existing platform
    convention). Missing scopes return ``HTTP 403`` with a structured
    body listing the gap.
    """
    expected = tuple(required)

    async def _dep(user: AdminUser = Depends(require_admin)) -> AdminUser:
        if user.has_scope(SCOPE_ADMIN_CLUSTER):
            return user
        missing = [scope for scope in expected if scope not in user.scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "insufficient_scope",
                    "error_description": f"missing scope(s): {missing}",
                    "required": list(expected),
                    "granted": sorted(user.scopes),
                },
            )
        return user

    return _dep


def filter_resources_for_admin(
    items: list,
    user: AdminUser,
    *,
    id_getter: Callable[[Any], str | None] | None = None,
) -> list:
    """Apply resource-scoped filtering using the admin's JWT payload."""
    if user.is_anonymous or user.has_scope(SCOPE_ADMIN_CLUSTER):
        return list(items)
    return core_filter_resources(items, user.payload, id_getter=id_getter)


__all__ = [
    "AdminUser",
    "filter_resources_for_admin",
    "require_admin",
    "require_admin_scope",
    "reset_admin_validator",
]
