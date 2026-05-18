"""Tests for :mod:`aqp.auth.auth0_fastapi`."""
from __future__ import annotations

import sys
import types

import pytest

from aqp.auth.auth0_fastapi import get_auth0_fastapi, reset_auth0_fastapi


@pytest.fixture(autouse=True)
def _reset_auth0_singleton() -> None:
    reset_auth0_fastapi()
    yield
    reset_auth0_fastapi()


def _set_auth_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    provider: str,
    issuer: str,
    audience: str,
) -> None:
    from aqp.config import settings as _settings

    monkeypatch.setattr(_settings, "auth_provider", provider, raising=False)
    monkeypatch.setattr(_settings, "auth_oidc_issuer", issuer, raising=False)
    monkeypatch.setattr(_settings, "auth_oidc_audience", audience, raising=False)


def _install_fake_sdk(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    class FakeAuth0FastAPI:
        def __init__(self, *, domain: str, audience: str) -> None:
            calls.append((domain, audience))
            self.domain = domain
            self.audience = audience

    plugin_module = types.ModuleType("fastapi_plugin")
    sdk_module = types.ModuleType("fastapi_plugin.fast_api_client")
    sdk_module.Auth0FastAPI = FakeAuth0FastAPI
    plugin_module.fast_api_client = sdk_module

    monkeypatch.setitem(sys.modules, "fastapi_plugin", plugin_module)
    monkeypatch.setitem(sys.modules, "fastapi_plugin.fast_api_client", sdk_module)
    return calls


def test_returns_none_when_provider_not_auth0(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_auth_settings(
        monkeypatch,
        provider="msal_entra",
        issuer="https://tenant.auth0.com/",
        audience="https://api.example.com",
    )
    assert get_auth0_fastapi() is None


def test_returns_none_when_issuer_or_audience_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_auth_settings(
        monkeypatch,
        provider="auth0",
        issuer="",
        audience="https://api.example.com",
    )
    assert get_auth0_fastapi() is None

    _set_auth_settings(
        monkeypatch,
        provider="auth0",
        issuer="https://tenant.auth0.com/",
        audience="",
    )
    assert get_auth0_fastapi() is None


def test_constructs_and_caches_auth0_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_auth_settings(
        monkeypatch,
        provider="auth0",
        issuer="https://tenant.auth0.com/",
        audience="https://api.example.com",
    )
    calls = _install_fake_sdk(monkeypatch)

    first = get_auth0_fastapi()
    second = get_auth0_fastapi()

    assert first is not None
    assert second is first
    assert calls == [("tenant.auth0.com", "https://api.example.com")]


def test_failed_import_only_attempted_once_until_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_auth_settings(
        monkeypatch,
        provider="auth0",
        issuer="https://tenant.auth0.com/",
        audience="https://api.example.com",
    )
    monkeypatch.delitem(sys.modules, "fastapi_plugin", raising=False)
    monkeypatch.delitem(sys.modules, "fastapi_plugin.fast_api_client", raising=False)

    assert get_auth0_fastapi() is None

    calls = _install_fake_sdk(monkeypatch)
    assert get_auth0_fastapi() is None
    assert calls == []

    reset_auth0_fastapi()
    rebuilt = get_auth0_fastapi()
    assert rebuilt is not None
    assert calls == [("tenant.auth0.com", "https://api.example.com")]
