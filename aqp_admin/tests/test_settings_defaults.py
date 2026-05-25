"""Settings defaults for local-vs-remote auth behavior."""
from __future__ import annotations

import pytest

from aqp_admin.settings import get_settings, reset_settings_cache


@pytest.fixture(autouse=True)
def _reset_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "AQP_ADMIN_AUTH_REQUIRED",
        "AQP_ADMIN_API_URL",
        "AQP_ADMIN_CONTROL_PLANE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_local_defaults_disable_auth() -> None:
    settings = get_settings()
    assert settings.api_url == "http://localhost:8000"
    assert settings.control_plane_url == "http://localhost:9000"
    assert settings.auth_required is False
    assert settings.auth_enabled is False


def test_explicit_auth_required_still_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AQP_ADMIN_AUTH_REQUIRED", "true")
    reset_settings_cache()
    settings = get_settings()
    assert settings.auth_required is True
    assert settings.auth_enabled is True


def test_non_local_topology_keeps_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AQP_ADMIN_API_URL", "https://api.aqp.fund")
    monkeypatch.setenv("AQP_ADMIN_CONTROL_PLANE_URL", "https://manage.aqp.fund")
    reset_settings_cache()
    settings = get_settings()
    assert settings.auth_required is True
    assert settings.auth_enabled is True
