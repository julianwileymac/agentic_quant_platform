"""Tests for :mod:`aqp.api.security_stepup` (AGENTS hard rule 52)."""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from aqp.api.security_stepup import (
    ACR_MFA,
    AMR_MFA,
    DEFAULT_STEP_UP_MAX_AGE_SECONDS,
    _coerce_amr,
    _coerce_auth_time,
    _has_mfa,
    _is_fresh,
    _stepup_www_authenticate,
    require_mfa,
    require_step_up,
    step_up_state,
)
from aqp.auth import CurrentUser, RequestContext
from aqp.auth.user import default_user


# ---------------------------------------------------------------------------
# Pure-helper unit tests (no FastAPI machinery)
# ---------------------------------------------------------------------------


def test_coerce_amr_accepts_list_and_scalar() -> None:
    assert _coerce_amr({"amr": ["pwd", "mfa"]}) == frozenset({"pwd", "mfa"})
    assert _coerce_amr({"amr": "mfa"}) == frozenset({"mfa"})
    assert _coerce_amr({"amr": [123, "pwd"]}) == frozenset({"pwd"})
    assert _coerce_amr({}) == frozenset()


def test_has_mfa_detects_standard_and_acr() -> None:
    assert _has_mfa({"amr": ["mfa"]}) is True
    assert _has_mfa({"amr": ["otp"]}) is True
    assert _has_mfa({"amr": ["hwk"]}) is True
    assert _has_mfa({"acr": ACR_MFA}) is True
    assert _has_mfa({"amr": ["pwd"]}) is False
    assert _has_mfa({}) is False


def test_coerce_auth_time_handles_str_int_none() -> None:
    assert _coerce_auth_time({"auth_time": 12345}) == 12345
    assert _coerce_auth_time({"auth_time": "67890"}) == 67890
    assert _coerce_auth_time({"auth_time": "bogus"}) is None
    assert _coerce_auth_time({}) is None


def test_is_fresh_window() -> None:
    now = int(time.time())
    assert _is_fresh({"auth_time": now - 30}, max_age_seconds=180) is True
    assert _is_fresh({"auth_time": now - 200}, max_age_seconds=180) is False
    assert _is_fresh({}, max_age_seconds=180) is False
    # Clock skew tolerance: token timestamps slightly in the future
    # are accepted up to 60 seconds.
    assert _is_fresh({"auth_time": now + 30}, max_age_seconds=180) is True


def test_www_authenticate_header_shape() -> None:
    value = _stepup_www_authenticate(max_age_seconds=180, error_description="needs mfa")
    assert value.startswith('Bearer error="insufficient_user_authentication"')
    assert 'acr_values="' in value
    assert ACR_MFA in value
    assert 'max_age="180"' in value
    assert 'error_description="needs mfa"' in value


# ---------------------------------------------------------------------------
# Dep wiring — exercise require_step_up + require_mfa with stub claims
# ---------------------------------------------------------------------------


def _make_app(dep, *, claims: dict[str, Any] | None) -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    def protected(_: CurrentUser = Depends(dep)) -> dict[str, Any]:
        return {"ok": True}

    # Override the auth chain. We bypass `current_user` /
    # `current_context` so the test is hermetic.
    async def fake_current_user(request: Request) -> CurrentUser:
        # Stash claims onto request.state to mimic the OIDC dep
        request.state.oidc_claims = claims
        # A non-default user so the step-up bypass for default-user
        # doesn't kick in.
        return CurrentUser(
            id="user-1",
            email="user@example.com",
            display_name="User One",
            auth_provider="auth0",
            auth_subject="auth0|abc",
            status="active",
            memberships=[],
            is_default=False,
        )

    async def fake_current_context() -> RequestContext:
        from aqp.auth.context import default_context

        return default_context()

    from aqp.api import security as _security
    from aqp.auth import deps as _deps

    app.dependency_overrides[_security.require_authenticated] = fake_current_user
    app.dependency_overrides[_deps.current_context] = fake_current_context
    return app


def test_require_step_up_rejects_when_no_claims() -> None:
    dep = require_step_up()
    app = _make_app(dep, claims=None)
    client = TestClient(app)
    resp = client.get("/protected")
    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers
    assert ACR_MFA in resp.headers["WWW-Authenticate"]


def test_require_step_up_rejects_when_no_mfa() -> None:
    dep = require_step_up()
    app = _make_app(dep, claims={"amr": ["pwd"], "auth_time": int(time.time())})
    client = TestClient(app)
    resp = client.get("/protected")
    assert resp.status_code == 401
    assert "fresh MFA required" in resp.json()["detail"]


def test_require_step_up_rejects_when_stale() -> None:
    dep = require_step_up(max_age_seconds=30)
    app = _make_app(
        dep,
        claims={"amr": ["mfa"], "auth_time": int(time.time()) - 600},
    )
    client = TestClient(app)
    resp = client.get("/protected")
    assert resp.status_code == 401
    assert 'max_age="30"' in resp.headers["WWW-Authenticate"]


def test_require_step_up_accepts_fresh_mfa() -> None:
    dep = require_step_up()
    app = _make_app(
        dep,
        claims={"amr": ["mfa", "pwd"], "auth_time": int(time.time()) - 30},
    )
    client = TestClient(app)
    resp = client.get("/protected")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_require_mfa_independent_of_freshness() -> None:
    dep = require_mfa()
    # Old auth_time but MFA was used at login — accept.
    app = _make_app(
        dep,
        claims={"amr": ["mfa"], "auth_time": int(time.time()) - 99999},
    )
    client = TestClient(app)
    resp = client.get("/protected")
    assert resp.status_code == 200


def test_local_default_user_bypasses_step_up() -> None:
    """Local dev (auth_provider=local) ALWAYS bypasses step-up."""
    dep = require_step_up()
    app = FastAPI()

    @app.get("/protected")
    def protected(_: CurrentUser = Depends(dep)) -> dict[str, Any]:
        return {"ok": True}

    async def fake_default_user(request: Request) -> CurrentUser:
        request.state.oidc_claims = None
        return default_user()

    async def fake_current_context() -> RequestContext:
        from aqp.auth.context import default_context

        return default_context()

    from aqp.api import security as _security
    from aqp.auth import deps as _deps

    app.dependency_overrides[_security.require_authenticated] = fake_default_user
    app.dependency_overrides[_deps.current_context] = fake_current_context
    client = TestClient(app)
    assert client.get("/protected").status_code == 200


def test_step_up_state_diagnostic_shape() -> None:
    """`step_up_state` returns a JSON-safe diagnostic snapshot."""
    from starlette.requests import Request as StarletteRequest

    fake_request = StarletteRequest(scope={"type": "http", "headers": []})
    fake_request.state.oidc_claims = {
        "amr": ["mfa"],
        "auth_time": int(time.time()) - 10,
    }
    state = step_up_state(fake_request)
    assert state["enabled"] is True
    assert state["has_mfa"] is True
    assert state["fresh_within_default_window"] is True
    assert state["default_max_age_seconds"] == DEFAULT_STEP_UP_MAX_AGE_SECONDS
