"""FastAPI auth enforcement primitives — Phase 4 of the multi-tenant rollout.

Three layers, all built on top of :mod:`aqp.auth.deps`:

- :func:`require_authenticated` — drop-in re-export so route files
  don't need a second import.
- :func:`require_scope` — JWT scope / permissions / custom-claim
  enforcement. Reads ``scope`` (OAuth standard), ``permissions``
  (Auth0 RBAC array), and the AQP-namespaced ``https://aqp/roles``
  custom claim.
- :func:`require_membership` — Postgres-backed RBAC. Asserts the
  current user has at least ``min_role`` on the active scope
  (workspace / project / lab / team / org).

The :func:`secure_router` helper wraps :class:`fastapi.APIRouter` so a
route module opts in to "every endpoint requires auth" with one line.
The rollout sweep replaces ``router = APIRouter(...)`` with
``router = secure_router(...)`` on each module that isn't on the
:data:`PUBLIC_ROUTERS` allowlist.

Enforcement mode (``AQP_AUTH_ENFORCE``):

- ``strict`` (default in production): 401/403 on every violation.
- ``permissive``: logs the violation + emits an OTEL span attribute
  but still allows the request through. Used during the rollout so
  the dashboard can show every would-be denial before the cut-over.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status

from aqp.auth import (
    CurrentUser,
    RequestContext,
    current_context,
    current_user,
    require_authenticated as _require_authenticated_base,
)
from aqp.auth.user import user_can
from aqp.config import settings
from aqp.config.defaults import (
    SCOPE_LAB,
    SCOPE_ORG,
    SCOPE_PROJECT,
    SCOPE_TEAM,
    SCOPE_WORKSPACE,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bypass allowlist
# ---------------------------------------------------------------------------

# Routes that intentionally accept unauthenticated traffic. New
# entries require an explicit code review note explaining why.
PUBLIC_ROUTERS: frozenset[str] = frozenset(
    {
        "health",          # cluster + k8s probes
        "auth",            # /auth/login + /auth/callback + /auth/config
        "monitoring",      # node exporter scrape
        "invites_public",  # /tenancy/invites/{token}/accept public APIRouter marker
    }
)


# ---------------------------------------------------------------------------
# Enforcement mode
# ---------------------------------------------------------------------------


def _is_strict() -> bool:
    mode = str(getattr(settings, "auth_enforce", "strict") or "strict").lower()
    return mode == "strict"


def _violation(
    *,
    code: int,
    detail: str,
    request: Request | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    """Either raise (strict) or log + tag the OTEL span (permissive)."""
    if _is_strict():
        raise HTTPException(status_code=code, detail=detail, headers=headers or {})
    logger.warning(
        "auth.violation code=%s detail=%r path=%s",
        code,
        detail,
        getattr(request, "url", None) if request else None,
    )
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]

        span = trace.get_current_span()
        if span is not None and span.is_recording():
            span.set_attribute("aqp.auth.would_deny", True)
            span.set_attribute("aqp.auth.would_deny_code", code)
            span.set_attribute("aqp.auth.would_deny_detail", detail)
    except Exception:  # pragma: no cover - OTEL optional
        return


# ---------------------------------------------------------------------------
# require_authenticated
# ---------------------------------------------------------------------------


def require_authenticated(
    user: CurrentUser = Depends(current_user),
    request: Request = None,  # type: ignore[assignment]
) -> CurrentUser:
    """Reject unauthenticated traffic (strict) or log it (permissive).

    Drop-in replacement for :func:`aqp.auth.deps.require_authenticated`
    that honours :attr:`Settings.auth_enforce`.
    """
    try:
        return _require_authenticated_base(user)
    except HTTPException as exc:
        if _is_strict():
            raise
        logger.warning(
            "auth.violation status=%s detail=%r path=%s",
            exc.status_code,
            exc.detail,
            getattr(request, "url", None) if request else None,
        )
        return user


# ---------------------------------------------------------------------------
# require_scope
# ---------------------------------------------------------------------------


def _namespaced_claim(claims: dict, name: str) -> object:
    """Return ``claims[<ns><name>]`` for the canonical namespace or any alias.

    Per ADR 003 the canonical namespace is ``settings.auth_claims_namespace``
    (default ``https://aqp.internal/``); legacy tokens issued before the
    migration window may still carry ``settings.auth_claims_namespace_aliases``
    entries (default ``["https://aqp/"]``).
    """
    namespaces = [str(settings.auth_claims_namespace or "https://aqp.internal/")]
    aliases = getattr(settings, "auth_claims_namespace_aliases", None) or []
    for alias in aliases:
        if alias:
            namespaces.append(str(alias))
    for ns in namespaces:
        if not ns.endswith("/"):
            ns = ns + "/"
        key = f"{ns}{name}"
        if key in claims:
            return claims[key]
    return None


def _granted_scopes_for(user: CurrentUser, request: Request | None) -> set[str]:
    """Best-effort union of JWT-derived and DB-derived scopes.

    Sources (in priority order):

    - OAuth standard ``scope`` claim (space-separated string).
    - Auth0 RBAC ``permissions`` claim (array of strings).
    - AQP-namespaced custom claim ``<ns>scopes`` (array) — canonical or alias.
    - AQP-namespaced custom claim ``<ns>roles`` (array) — expanded via the
      four-role lattice from ``aqp_platform_core.auth.rbac`` (ADR 003):
        aqp-viewer     -> read:infrastructure
        aqp-operator   -> + manage:agents
        aqp-admin      -> + manage:infrastructure
        aqp-superadmin -> + admin:cluster
      Legacy role names (admin/owner/editor/viewer) retain their pre-Phase-4
      data:* mapping.
    - Local-default users get ``data:read`` + ``data:write`` so the
      local dev loop keeps working.
    """
    scopes: set[str] = set()
    if request is not None:
        claims = getattr(request.state, "oidc_claims", None)
        # Phase D of the Management Engine: merge Cloudflare Access
        # claims when the request entered through a Cloudflare Tunnel
        # + Access app. Lazy-imported because the provider module
        # depends on optional crypto libs and we don't want to take a
        # hard import dep at the security-layer boot path.
        try:
            from aqp.auth.providers.cloudflare_access import (
                extract_cloudflare_access_claims,
            )

            cf_claims = extract_cloudflare_access_claims(request)
        except Exception:  # noqa: BLE001
            cf_claims = None
        if isinstance(cf_claims, dict):
            # Stash on request.state for downstream consumers + merge
            # into the active claims bundle so role / scope expansion
            # picks them up like any other OIDC claim.
            request.state.cf_access_claims = cf_claims
            if not isinstance(claims, dict):
                claims = dict(cf_claims)
            else:
                # Cloudflare Access claims take precedence on collision
                # because the edge is the trust boundary closest to the
                # user, but we keep the upstream OIDC sub when present.
                merged = dict(cf_claims)
                merged.update({k: v for k, v in claims.items() if k not in merged})
                claims = merged
        if isinstance(claims, dict):
            scope_str = claims.get("scope")
            if isinstance(scope_str, str):
                scopes.update(scope_str.split())
            # Auth0 RBAC permissions array — flat.
            permissions = claims.get("permissions")
            if isinstance(permissions, list):
                scopes.update(str(s) for s in permissions if isinstance(s, str))
            # AQP-namespaced ``scopes`` claim (array).
            ns_scopes = _namespaced_claim(claims, "scopes")
            if isinstance(ns_scopes, list):
                scopes.update(str(s) for s in ns_scopes if isinstance(s, str))
            # AQP-namespaced ``roles`` claim (array) -> scope expansion.
            ns_roles = _namespaced_claim(claims, "roles")
            if isinstance(ns_roles, list):
                # Phase 1 of the AQP control-plane maturation moved the
                # canonical scope expansion behind
                # :func:`aqp.auth.scopes.expand_role_canonical`, which
                # accepts BOTH the platform ``aqp-*`` flavour and the
                # legacy tenancy ``viewer / editor / admin / owner``
                # flavour and translates the legacy ones via
                # :func:`legacy_role_to_aqp_role` before expanding.
                # That closes the empty-claim drift bug where a JWT
                # carrying only ``editor`` ended up with no scopes.
                try:
                    from aqp.auth.scopes import expand_role_canonical

                    for role in ns_roles:
                        scopes.update(expand_role_canonical(str(role)))
                except Exception:  # noqa: BLE001
                    pass
                # Legacy role names continue to grant data:* / admin so
                # existing routes don't break during the migration window.
                # The legacy lattice mirrors the role-rank ordering in
                # ``aqp.config.defaults`` (viewer < editor < admin <
                # owner). The canonical expansion above is authoritative;
                # this block remains as a belt-and-suspenders override
                # for tokens that pre-date the rbac extension.
                for role in ns_roles:
                    role_str = str(role).lower()
                    if role_str in ("admin", "owner"):
                        scopes.update({"data:read", "data:write", "admin"})
                    elif role_str == "editor":
                        scopes.update({"data:read", "data:write"})
                    elif role_str == "viewer":
                        scopes.add("data:read")
    if user.is_default:
        # Local-first dev never has an Authorization header; treat the
        # default user as fully scoped so existing test fixtures keep
        # passing. Production deploys gate this by setting
        # ``AQP_AUTH_PROVIDER=auth0`` so the default user can't exist.
        scopes.update({"data:read", "data:write"})
    return scopes


def filter_resources_for_user(
    items: list,
    request: Request | None,
    *,
    id_getter=None,
) -> list:
    """Apply :func:`aqp_platform_core.auth.resource_filter.filter_resources`.

    Drop-in helper for FastAPI routes that need resource-scoped list
    filtering (ADR 003). Reads OIDC claims from
    ``request.state.oidc_claims``; pass-through when no claims are
    present (local default user).
    """
    from aqp_platform_core.auth import filter_resources

    if request is None:
        return list(items)
    claims = getattr(request.state, "oidc_claims", None)
    if not isinstance(claims, dict):
        return list(items)
    return filter_resources(items, claims, id_getter=id_getter)


def require_scope(*required: str) -> Callable[..., CurrentUser]:
    """Build a dep that asserts every scope in *required* is granted.

    Example::

        @router.post("/datasets/upload")
        async def upload(
            payload: UploadIn,
            user: CurrentUser = Depends(require_scope("data:write")),
        ):
            ...
    """
    required_set = tuple(required)

    def _dep(
        request: Request,
        user: CurrentUser = Depends(require_authenticated),
    ) -> CurrentUser:
        granted = _granted_scopes_for(user, request)
        missing = [s for s in required_set if s not in granted]
        if missing:
            _violation(
                code=status.HTTP_403_FORBIDDEN,
                detail=f"missing scope(s): {missing}",
                request=request,
            )
        return user

    return _dep


# ---------------------------------------------------------------------------
# require_membership
# ---------------------------------------------------------------------------


_SCOPE_KEY_MAP: dict[str, str] = {
    "org": SCOPE_ORG,
    "team": SCOPE_TEAM,
    "workspace": SCOPE_WORKSPACE,
    "project": SCOPE_PROJECT,
    "lab": SCOPE_LAB,
}


def require_membership(
    min_role: str = "viewer",
    scope: str = "workspace",
) -> Callable[..., RequestContext]:
    """Dep that asserts ``user_can(user, min_role, scope_kind=scope, scope_id=ctx.<scope>_id)``.

    The ``scope`` argument picks which id on :class:`RequestContext` is
    checked. Common values:

    - ``"org"``: checks ``ctx.org_id``.
    - ``"team"``: checks ``ctx.team_id``.
    - ``"workspace"`` (default): checks ``ctx.workspace_id``.
    - ``"project"``: checks ``ctx.project_id``.
    - ``"lab"``: checks ``ctx.lab_id``.
    """
    scope_kind = _SCOPE_KEY_MAP.get(scope.lower(), SCOPE_WORKSPACE)

    def _dep(
        request: Request,
        user: CurrentUser = Depends(require_authenticated),
        ctx: RequestContext = Depends(current_context),
    ) -> RequestContext:
        from aqp.auth.context import scope_id_for

        scope_id = scope_id_for(ctx, scope_kind)
        if not scope_id:
            _violation(
                code=status.HTTP_400_BAD_REQUEST,
                detail=f"active {scope} required for this operation",
                request=request,
            )
            return ctx
        if not user_can(
            user, min_role, scope_kind=scope_kind, scope_id=scope_id
        ):
            _violation(
                code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"role {min_role!r} required on {scope} {scope_id} "
                    f"(current memberships: "
                    f"{[m.get('role') for m in user.memberships]})"
                ),
                request=request,
            )
        return ctx

    return _dep


# ---------------------------------------------------------------------------
# secure_router
# ---------------------------------------------------------------------------


def secure_router(
    *,
    prefix: str = "",
    tags: list[str] | None = None,
    default_scope: str | None = None,
    extra_dependencies: list[Any] | None = None,
) -> APIRouter:
    """Build an :class:`APIRouter` with a default ``require_authenticated`` dep.

    Optional ``default_scope`` chains a :func:`require_scope` check
    onto every route. ``extra_dependencies`` lets a module add more
    deps without losing the default ones (e.g. an OTEL span tag).
    """
    deps: list[Any] = [Depends(require_authenticated)]
    if default_scope:
        deps.append(Depends(require_scope(default_scope)))
    if extra_dependencies:
        deps.extend(extra_dependencies)
    return APIRouter(
        prefix=prefix,
        tags=tags or [],
        dependencies=deps,
    )


# ---------------------------------------------------------------------------
# Phase 4d — DPoP (RFC 9449) per-route enforcement
# ---------------------------------------------------------------------------


def require_dpop_token() -> Callable[..., CurrentUser]:
    """Build a dep that requires the request to carry a ``DPoP`` proof header.

    DPoP (Demonstrating Proof-of-Possession, RFC 9449) binds an access
    token to a client-held key pair so a stolen Bearer token cannot be
    replayed by an attacker without the matching private key. The
    auth0-fastapi-api SDK's mixed-mode (``dpop_enabled=True``,
    ``dpop_required=False`` — see :mod:`aqp.auth.auth0_fastapi`)
    accepts both Bearer and DPoP-bound tokens globally; this
    dependency is the per-route escalation that REJECTS Bearer-only
    requests for the highest-value endpoints.

    Apply on top of the standard scope check::

        @router.post(
            "/apply",
            dependencies=[
                Depends(require_scope("terraform:apply")),
                Depends(require_dpop_token()),
            ],
        )
        async def apply(...): ...

    Feature-flagged via ``settings.dpop_enforcement_enabled``. Off by
    default to keep the existing operator workflow functional during
    cutover. Operators flip the flag to ``True`` once every client
    sending requests to the gated endpoints has migrated to a DPoP
    proof. Even when the flag is off, the dependency runs (so the
    surrounding auth chain still resolves) — it just doesn't reject.
    """

    def _dep(
        request: Request,
        user: CurrentUser = Depends(require_authenticated),
    ) -> CurrentUser:
        enforce = bool(getattr(settings, "dpop_enforcement_enabled", False))
        if not enforce:
            return user
        # The DPoP header carries the proof JWT. Presence of the
        # header is the cheap pre-check; the auth0-fastapi-api SDK
        # validates the proof's signature, audience, and binding
        # against the access token's `cnf.jkt` claim earlier in the
        # request lifecycle when the SDK is configured.
        dpop_header = request.headers.get("DPoP") or request.headers.get("dpop")
        if not dpop_header:
            _violation(
                code=status.HTTP_401_UNAUTHORIZED,
                detail="DPoP proof required for this endpoint",
                request=request,
                headers={"WWW-Authenticate": 'DPoP error="invalid_request"'},
            )
            return user
        return user

    return _dep


__all__ = [
    "PUBLIC_ROUTERS",
    "filter_resources_for_user",
    "require_authenticated",
    "require_dpop_token",
    "require_membership",
    "require_scope",
    "secure_router",
]
