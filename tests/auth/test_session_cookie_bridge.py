"""Tests for the Phase 0 cookie -> current_user bridge.

Covers the path documented in ``aqp_docs/docs/concepts/identity/identity.md`` lines 73-74 where the
``aqp_session`` cookie set by ``/auth/callback`` is decrypted on
subsequent requests so server-rendered pages don't have to repeat the
Bearer flow.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aqp.auth.deps import _token_from_session_cookie
from aqp.auth.session import (
    EncryptedCookieStateStore,
    session_payload_from_tokens,
)
from aqp.config import settings

jwcrypto = pytest.importorskip("jwcrypto", reason="jwcrypto extra not installed")


SECRET = "0123456789abcdef0123456789abcdef"  # 32 chars; jwcrypto-friendly


def _request(cookies: dict[str, str]) -> MagicMock:
    request = MagicMock()
    request.cookies = cookies
    return request


def test_returns_none_when_secret_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_session_secret", "")
    assert _token_from_session_cookie(_request({"aqp_session": "anything"})) is None


def test_returns_none_when_cookie_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_session_secret", SECRET)
    assert _token_from_session_cookie(_request({})) is None


def test_returns_none_when_cookie_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_session_secret", SECRET)
    monkeypatch.setattr(settings, "auth_session_cookie", "aqp_session")
    assert (
        _token_from_session_cookie(_request({"aqp_session": "not-a-real-jwe"})) is None
    )


def test_returns_access_token_from_valid_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_session_secret", SECRET)
    monkeypatch.setattr(settings, "auth_session_cookie", "aqp_session")

    store = EncryptedCookieStateStore(secret=SECRET, cookie_name="aqp_session")
    payload = session_payload_from_tokens(
        user_claims={"sub": "auth0|abc", "email": "alice@example.com"},
        access_token="access-jwt-token",
        id_token="id-jwt",
        refresh_token=None,
        audience="https://aqp.local/api",
        expires_in=3600,
        scope="openid profile",
    )
    # /auth/callback mints with the cookie name as the salt so
    # current_user can read it back without knowing the OAuth state.
    cookie_value = store.set("aqp_session", payload)

    out = _token_from_session_cookie(_request({"aqp_session": cookie_value}))
    assert out == "access-jwt-token"


def test_returns_none_when_decrypted_payload_has_no_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_session_secret", SECRET)
    monkeypatch.setattr(settings, "auth_session_cookie", "aqp_session")

    store = EncryptedCookieStateStore(secret=SECRET, cookie_name="aqp_session")
    cookie_value = store.set(
        "aqp_session",
        {"user": {"sub": "x"}, "token_sets": []},
    )
    assert _token_from_session_cookie(_request({"aqp_session": cookie_value})) is None


def test_legacy_top_level_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Older session payloads stored the access token at the top level."""
    monkeypatch.setattr(settings, "auth_session_secret", SECRET)
    monkeypatch.setattr(settings, "auth_session_cookie", "aqp_session")

    store = EncryptedCookieStateStore(secret=SECRET, cookie_name="aqp_session")
    cookie_value = store.set(
        "aqp_session",
        {"user": {"sub": "x"}, "access_token": "legacy-token"},
    )
    out = _token_from_session_cookie(_request({"aqp_session": cookie_value}))
    assert out == "legacy-token"
