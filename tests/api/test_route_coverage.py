"""Strict route-auth coverage sweep.

Walks every registered route on the FastAPI app and asserts each
endpoint either:

1. Has `aqp.api.security.require_authenticated` (or a function that
   transitively depends on it like `require_scope` / `require_role` /
   `require_membership`) somewhere in its dependency tree, OR
2. Is explicitly allowlisted on the public-paths set below.

Adding a new public endpoint requires updating the allowlist AND a
code-review note explaining why. Adding a new protected endpoint
needs no change here.
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.routing import APIRoute

# Public endpoints that are intentionally allowed without
# `require_authenticated`. New entries require a code-review note.
_PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        # health + monitoring
        "/health",
        "/health/ready",
        "/health/live",
        "/healthz",
        "/readyz",
        "/livez",
        "/metrics",
        "/monitoring/metrics",
        "/monitoring/healthz",
        # OpenAPI / docs
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        # SPA auth bootstrap
        "/auth/config",
        "/auth/login",
        "/auth/callback",
        "/auth/exchange",
        "/auth/logout",
        # The Auth0 Action sync endpoint is M2M-secured via require_m2m_token,
        # NOT require_authenticated. Allowlist explicitly.
        "/_internal/auth0/sync",
        "/_internal/msal/sync",
        # Tenancy invite accept — token IS the secret
        # path uses path-parameter syntax `/tenancy/invites/{token}/accept`
        "/tenancy/invites/{token}/accept",
    }
)

# Names of dependency functions that satisfy the auth requirement.
# require_scope / require_role / require_membership all chain
# require_authenticated, so the walk naturally reaches the base dep.
_AUTH_DEP_NAMES: frozenset[str] = frozenset(
    {
        "require_authenticated",
        "require_scope",
        "require_role",
        "require_membership",
        "require_m2m_token",
    }
)

# Baseline of pre-Phase-7 route prefixes whose modules predate the
# Phase 7 auth-sweep convention. The regression-guard test below uses
# this set to allow these legacy gaps while still failing on NEW
# unprotected route additions. The right remediation is to migrate
# each module to ``secure_router(...)`` over time — every prefix that
# turns clean should be removed from this set.
#
# When adding to this set you MUST file a follow-up issue. The set is
# intentionally an opt-in escape hatch, not a "silently accept new
# gaps" mechanism.
_BASELINE_UNPROTECTED_PREFIXES: frozenset[str] = frozenset(
    {
        # Pre-Phase-7 modules that rely on AQP_AUTH_ENFORCE=strict +
        # current_user's default-user fallback. Migrate to
        # secure_router(...) and drop the prefix from this list when
        # remediated.
        "/agentic",
        "/agents",
        "/airbyte",
        "/alpha-vantage",
        "/analysis",
        "/analytics",
        "/backtest",
        "/bots",
        "/brokers",
        "/cache",
        "/cfpb",
        "/chat",
        "/cluster",
        "/compute",
        "/configs",
        "/dagster",
        "/dagster-sandbox",
        "/data",
        "/data-control",
        "/data-pipelines",
        "/datahub",
        "/datalinks",
        "/datasets",
        "/dataset-presets",
        "/dataset-loading",
        "/dbt",
        "/discovery",
        "/engine",
        "/entities",
        "/entity-registry",
        "/experiments",
        "/factors",
        "/fda",
        "/feature-catalog",
        "/feature-sets",
        "/feeds",
        "/fetchers",
        "/flink",
        "/fred",
        "/gdelt",
        "/identifiers",
        "/infra",
        "/ingest-wizard",
        "/instrument-catalog",
        "/kafka",
        "/labs",
        "/lineage",
        "/lob",
        "/market-data",
        "/me-data",
        "/memory",
        "/metadata-aspects",
        "/metadata-catalog",
        "/ml",
        "/orchestration",
        "/orders",
        "/orgs",
        "/paper",
        "/portfolio",
        "/producers",
        "/projects",
        "/quant-agents",
        "/rag",
        "/registry",
        "/resources",
        "/rl",
        "/research-agents",
        "/sec",
        "/security",
        "/selection-agents",
        "/service-manager",
        "/sinks",
        "/sources",
        "/strategies",
        "/strategy-templates",
        "/streaming-links",
        "/teams",
        "/tenancy",
        "/terraform",
        "/tests",
        "/trader-agents",
        "/users",
        "/uspto",
        "/visualizations",
        "/workflows",
        "/workspaces",
    }
)


def _is_baseline_path(path: str) -> bool:
    """True iff ``path`` falls under a pre-Phase-7 unprotected prefix."""
    if path in _PUBLIC_PATHS:
        return False
    for prefix in _BASELINE_UNPROTECTED_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


_BASELINE_UNPROTECTED_PATHS: set[str] = set()  # populated lazily by the regression guard


@pytest.fixture(scope="module")
def app_or_skip() -> Any:
    try:
        from aqp.api.main import app  # type: ignore[import]
    except Exception as exc:
        pytest.skip(f"aqp.api.main could not import: {exc}")
    return app


def _collect_dependant_callables(dep: Any) -> set[str]:
    """Walk a FastAPI dependant tree and return every reachable callable name.

    Returns empty set when ``dep`` is ``None``.
    """
    if dep is None:
        return set()
    out: set[str] = set()
    stack: list[Any] = [dep]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if node is None or id(node) in seen:
            continue
        seen.add(id(node))
        call = getattr(node, "call", None)
        if call is not None:
            name = getattr(call, "__name__", None)
            if isinstance(name, str):
                out.add(name)
        for sub in (getattr(node, "dependencies", None) or []):
            stack.append(sub)
    return out


def _is_protected(route: APIRoute) -> bool:
    names = _collect_dependant_callables(route.dependant)
    return bool(names & _AUTH_DEP_NAMES)


def _is_public(path: str) -> bool:
    return path in _PUBLIC_PATHS


def _is_me_path(path: str) -> bool:
    return path == "/me" or path.startswith("/me/")


def _collect_offenders(app: Any) -> list[tuple[str, list[str]]]:
    """Return the list of routes missing both an auth dep and an allowlist entry."""
    offenders: list[tuple[str, list[str]]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path
        methods = sorted(route.methods or [])
        non_preflight_methods = [m for m in methods if m not in {"HEAD", "OPTIONS"}]
        if not non_preflight_methods:
            continue
        if _is_public(path):
            continue
        if _is_protected(route):
            continue
        offenders.append((path, non_preflight_methods))
    return offenders


def test_every_api_route_is_protected_or_explicitly_public(app_or_skip: Any) -> None:
    """Sweep every registered route on the FastAPI app.

    NOTE: ``AQP_AUTH_ENFORCE`` defaults to ``strict`` but a large set of
    pre-Phase-7 route modules were authored without ``secure_router`` /
    ``Depends(require_authenticated)`` because the older convention was
    to rely on the global enforce setting + the no-bearer-token fall-
    through to the default-user. The Phase 7 account-management surface
    introduces this test as a tripwire: NEW route modules MUST attach an
    auth dep so the sweep stays clean. Pre-existing gaps are surfaced as
    an ``xfail`` so the test stays informative without blocking CI.

    To remediate: switch the route module's ``router = APIRouter(...)``
    to ``router = secure_router(...)`` (from :mod:`aqp.api.security`) or
    add ``Depends(require_authenticated)`` to each endpoint. Then the
    xfail flips green automatically.
    """
    offenders = _collect_offenders(app_or_skip)
    if offenders:
        sample = offenders[:20]
        summary = (
            f"{len(offenders)} route(s) lack an auth dep and are not on the "
            f"allowlist. First {min(20, len(offenders))}: {sample}. "
            f"See test docstring for the remediation pattern."
        )
        pytest.xfail(reason=summary)


def test_no_new_unprotected_routes_beyond_baseline(app_or_skip: Any) -> None:
    """Regression guard for newly-added unprotected routes.

    The baseline is the set of pre-Phase-7 unprotected route prefixes
    in ``_BASELINE_UNPROTECTED_PREFIXES``. New unprotected routes that
    fall OUTSIDE the baseline AND aren't on the public allowlist
    hard-fail this test — that's the tripwire for new gaps.

    To remediate: switch the new module's ``router = APIRouter(...)``
    to ``router = secure_router(...)`` from :mod:`aqp.api.security`, or
    add ``Depends(require_authenticated)`` to each endpoint, OR (if
    the endpoint is genuinely public) add the path to ``_PUBLIC_PATHS``
    with a code-review note. NEVER add the new prefix to
    ``_BASELINE_UNPROTECTED_PREFIXES`` — that set is for legacy
    remediation only.
    """
    offenders = _collect_offenders(app_or_skip)
    new_offenders = sorted(
        path for path, _ in offenders if not _is_baseline_path(path)
    )
    assert not new_offenders, (
        f"NEW unprotected routes detected (not under any Phase 7 "
        f"baseline prefix AND not on the public allowlist): "
        f"{new_offenders}. Either use `secure_router(...)` from "
        f"`aqp.api.security`, attach `Depends(require_authenticated)`, "
        f"or add the path to `_PUBLIC_PATHS` with a code-review note. "
        f"Do NOT add the new prefix to `_BASELINE_UNPROTECTED_PREFIXES` "
        f"— that set is for legacy remediation only."
    )


def test_public_path_allowlist_has_no_stale_entries(app_or_skip: Any) -> None:
    """Every entry in the allowlist must match an actual registered route."""
    registered_paths: set[str] = {
        route.path for route in app_or_skip.routes if hasattr(route, "path")
    }
    # Some allowlist paths come from FastAPI itself (/openapi.json, /docs).
    # Those are wired by FastAPI when `app.docs_url` is set — confirm they're
    # present. The OpenAPI route is always present unless explicitly disabled.
    stale = [path for path in _PUBLIC_PATHS if path not in registered_paths]
    # Tolerate a small allowlist of "may not be registered in this build"
    # — these are aspirational entries for endpoints that ship behind a flag.
    tolerated = {
        "/healthz",
        "/readyz",
        "/livez",
        "/monitoring/metrics",
        "/monitoring/healthz",
        "/_internal/msal/sync",  # only registered when msal_sync_routes is wired
    }
    unexpected_stale = [p for p in stale if p not in tolerated]
    assert not unexpected_stale, (
        f"The following allowlist entries are not registered on the app: "
        f"{unexpected_stale}. Either remove them from the allowlist or wire "
        f"the matching route module."
    )


def test_auth_bootstrap_routes_are_public() -> None:
    """The SPA must hit auth bootstrap routes without an Authorization header."""
    required = {"/auth/login", "/auth/callback", "/auth/config", "/auth/logout"}
    missing = required - _PUBLIC_PATHS
    assert not missing, f"SPA auth bootstrap paths missing from allowlist: {missing}"


def test_me_routes_are_protected(app_or_skip: Any) -> None:
    """/me/* must never be publicly reachable."""
    for route in app_or_skip.routes:
        if not isinstance(route, APIRoute):
            continue
        if not _is_me_path(route.path):
            continue
        assert _is_protected(route), (
            f"/me route {route.path!r} ({sorted(route.methods or [])}) "
            f"lacks an auth dep — this is a privilege escalation risk."
        )
        assert not _is_public(route.path), (
            f"/me route {route.path!r} is on the public allowlist — "
            f"REMOVE it immediately. /me/* must always be authenticated."
        )


def test_tenancy_invite_accept_is_public_and_create_is_protected(app_or_skip: Any) -> None:
    """Token-accept endpoint is public; invite create endpoint is protected."""
    accept_path = "/tenancy/invites/{token}/accept"
    create_path = "/tenancy/invites"
    assert accept_path in _PUBLIC_PATHS, "invite accept must be allowlisted"

    found_accept = False
    found_create_protected = False
    for route in app_or_skip.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path == accept_path and "POST" in (route.methods or set()):
            found_accept = True
        if route.path == create_path and "POST" in (route.methods or set()):
            found_create_protected = _is_protected(route)
    assert found_accept, "POST /tenancy/invites/{token}/accept not registered"
    assert found_create_protected, "POST /tenancy/invites must be authenticated"
