"""Tests for the Phase 4 ``aqp.api.security`` module.

Covers require_scope / require_membership / secure_router /
permissive-vs-strict modes.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException

from aqp.api.security import (
    require_authenticated,
    require_membership,
    require_scope,
    secure_router,
)
from aqp.auth.user import CurrentUser
from aqp.config import settings


def _user(*, is_default: bool = False, memberships=None) -> CurrentUser:
    return CurrentUser(
        id="user-7",
        email="u@example.com",
        display_name="U",
        is_default=is_default,
        memberships=memberships or [],
    )


# ---------------------------------------------------------------------------
# require_scope
# ---------------------------------------------------------------------------


def test_require_scope_allows_when_jwt_claims_contain_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_enforce", "strict")
    request = MagicMock()
    request.state.oidc_claims = {"scope": "data:read data:write"}
    dep = require_scope("data:write")
    out = dep(request=request, user=_user())
    assert out.id == "user-7"


def test_require_scope_rejects_in_strict_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_enforce", "strict")
    request = MagicMock()
    request.state.oidc_claims = {"scope": "data:read"}
    dep = require_scope("data:write")
    with pytest.raises(HTTPException) as exc:
        dep(request=request, user=_user())
    assert exc.value.status_code == 403


def test_require_scope_permissive_logs_but_passes(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "auth_enforce", "permissive")
    request = MagicMock()
    request.state.oidc_claims = {"scope": "data:read"}
    dep = require_scope("data:write")
    with caplog.at_level("WARNING"):
        out = dep(request=request, user=_user())
    assert out.id == "user-7"
    assert any("auth.violation" in r.getMessage() for r in caplog.records)


def test_local_default_user_gets_read_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_enforce", "strict")
    request = MagicMock()
    request.state.oidc_claims = None
    dep = require_scope("data:write")
    out = dep(request=request, user=_user(is_default=True))
    assert out.is_default


def test_roles_claim_expands_to_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_enforce", "strict")
    request = MagicMock()
    request.state.oidc_claims = {"https://aqp/roles": ["admin"]}
    dep = require_scope("admin")
    out = dep(request=request, user=_user())
    assert out.id == "user-7"


# ---------------------------------------------------------------------------
# require_membership
# ---------------------------------------------------------------------------


def test_require_membership_passes_when_user_has_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.auth.context import RequestContext

    monkeypatch.setattr(settings, "auth_enforce", "strict")

    user = _user(
        memberships=[
            {"scope_kind": "workspace", "scope_id": "ws-1", "role": "editor", "live_control": False}
        ]
    )
    ctx = RequestContext(user_id="user-7", workspace_id="ws-1")
    request = MagicMock()
    dep = require_membership(min_role="viewer", scope="workspace")
    out = dep(request=request, user=user, ctx=ctx)
    assert out.workspace_id == "ws-1"


def test_require_membership_rejects_when_no_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.auth.context import RequestContext

    monkeypatch.setattr(settings, "auth_enforce", "strict")

    user = _user(
        memberships=[
            {"scope_kind": "workspace", "scope_id": "ws-other", "role": "viewer"}
        ]
    )
    ctx = RequestContext(user_id="user-7", workspace_id="ws-1")
    request = MagicMock()
    dep = require_membership(min_role="editor", scope="workspace")
    with pytest.raises(HTTPException) as exc:
        dep(request=request, user=user, ctx=ctx)
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# secure_router
# ---------------------------------------------------------------------------


def test_secure_router_attaches_authentication_dep() -> None:
    router = secure_router(prefix="/widgets", tags=["widgets"])
    # FastAPI stores router-level dependencies on .dependencies as a
    # list of Depends() objects; verify ours is in there.
    assert any(
        getattr(d, "dependency", None) is require_authenticated
        for d in router.dependencies
    )


def test_secure_router_optionally_chains_scope() -> None:
    router = secure_router(prefix="/w", default_scope="data:write")
    # We can't directly compare the closure produced by require_scope,
    # but we know there should be two router-level deps (auth + scope).
    assert len(router.dependencies) == 2
