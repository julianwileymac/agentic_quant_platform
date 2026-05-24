"""RFC 8707 audience validation tests (Workstream E).

Covers :mod:`aqp.api.mcp_audience` end-to-end:

- ``off`` mode no-ops on any input;
- ``permissive`` logs would-deny + returns successfully;
- ``strict`` raises 401 with RFC 9728 ``WWW-Authenticate`` header;
- audience set as a string vs. array is normalised;
- RFC 8707 ``resource`` claim is honoured alongside ``aud``.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _fake_request(claims: dict | None) -> SimpleNamespace:
    state = SimpleNamespace()
    if claims is not None:
        state.oidc_claims = claims
    request = SimpleNamespace()
    request.state = state
    request.url = SimpleNamespace(path="/mcp/data/tools/x/invoke")
    return request


def test_off_mode_no_ops(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.api.mcp_audience import validate_mcp_audience

    request = _fake_request({"aud": "other-resource"})
    # No raise even though audience does not include expected.
    validate_mcp_audience(
        request,
        "https://api.aqp.fund/mcp/data",
        mode="off",
    )


def test_strict_mode_rejects_mismatched_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.api.mcp_audience import validate_mcp_audience
    from aqp.config import settings

    monkeypatch.setattr(settings, "auth_provider", "auth0", raising=False)
    request = _fake_request({"aud": ["wrong"]})
    with pytest.raises(HTTPException) as exc:
        validate_mcp_audience(
            request,
            "https://api.aqp.fund/mcp/data",
            mode="strict",
        )
    assert exc.value.status_code == 401
    headers = exc.value.headers or {}
    assert "WWW-Authenticate" in headers
    assert "Bearer" in headers["WWW-Authenticate"]
    assert "resource_metadata=" in headers["WWW-Authenticate"]


def test_strict_mode_accepts_array_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.api.mcp_audience import validate_mcp_audience
    from aqp.config import settings

    monkeypatch.setattr(settings, "auth_provider", "auth0", raising=False)
    expected = "https://api.aqp.fund/mcp/data"
    request = _fake_request({"aud": ["other", expected, "more"]})
    # No raise.
    validate_mcp_audience(request, expected, mode="strict")


def test_strict_mode_accepts_string_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.api.mcp_audience import validate_mcp_audience
    from aqp.config import settings

    monkeypatch.setattr(settings, "auth_provider", "auth0", raising=False)
    expected = "https://api.aqp.fund/mcp/data"
    request = _fake_request({"aud": expected})
    validate_mcp_audience(request, expected, mode="strict")


def test_strict_mode_honours_resource_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    """RFC 8707: a non-standard ``resource`` claim is a stronger signal
    than ``aud`` because it cannot be aliased by a multi-aud token."""
    from aqp.api.mcp_audience import validate_mcp_audience
    from aqp.config import settings

    monkeypatch.setattr(settings, "auth_provider", "auth0", raising=False)
    expected = "https://api.aqp.fund/mcp/data"
    request = _fake_request({"aud": ["unrelated"], "resource": expected})
    validate_mcp_audience(request, expected, mode="strict")


def test_strict_mode_skips_local_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local dev loop has no OIDC envelope; validator must no-op."""
    from aqp.api.mcp_audience import validate_mcp_audience
    from aqp.config import settings

    monkeypatch.setattr(settings, "auth_provider", "local", raising=False)
    request = _fake_request({"aud": "other"})
    validate_mcp_audience(
        request,
        "https://api.aqp.fund/mcp/data",
        mode="strict",
    )


def test_permissive_mode_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Permissive logs + tags OTel but never raises."""
    from aqp.api.mcp_audience import validate_mcp_audience
    from aqp.config import settings

    monkeypatch.setattr(settings, "auth_provider", "auth0", raising=False)
    request = _fake_request({"aud": "wrong"})
    validate_mcp_audience(
        request,
        "https://api.aqp.fund/mcp/data",
        mode="permissive",
    )


def test_strict_mode_skips_when_claims_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default user (no Bearer at all) — earlier deps allowed it through."""
    from aqp.api.mcp_audience import validate_mcp_audience
    from aqp.config import settings

    monkeypatch.setattr(settings, "auth_provider", "auth0", raising=False)
    request = _fake_request(None)
    # No claims means require_authenticated was satisfied by the local
    # default user path; we must not double-deny.
    validate_mcp_audience(
        request,
        "https://api.aqp.fund/mcp/data",
        mode="strict",
    )


def test_strict_mode_normalises_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.api.mcp_audience import validate_mcp_audience
    from aqp.config import settings

    monkeypatch.setattr(settings, "auth_provider", "auth0", raising=False)
    request = _fake_request({"aud": "https://api.aqp.fund/mcp/data/"})
    validate_mcp_audience(
        request,
        "https://api.aqp.fund/mcp/data",
        mode="strict",
    )


def test_build_resource_metadata_header_namespaces_path() -> None:
    from aqp.api.mcp_audience import build_resource_metadata_header

    headers = build_resource_metadata_header("https://api.aqp.fund/mcp/data")
    assert "WWW-Authenticate" in headers
    value = headers["WWW-Authenticate"]
    assert (
        "resource_metadata="
        in value
    )
    # The metadata document URL is at /.well-known/oauth-protected-resource/<path>.
    assert "/.well-known/oauth-protected-resource/mcp/data" in value


def test_build_resource_metadata_header_root_when_no_path() -> None:
    from aqp.api.mcp_audience import build_resource_metadata_header

    headers = build_resource_metadata_header("https://api.aqp.fund")
    assert (
        '/.well-known/oauth-protected-resource"'
        in headers["WWW-Authenticate"]
    )


def test_build_resource_metadata_header_empty_when_uri_invalid() -> None:
    from aqp.api.mcp_audience import build_resource_metadata_header

    assert build_resource_metadata_header("") == {}
    assert build_resource_metadata_header("not-a-uri") == {}
