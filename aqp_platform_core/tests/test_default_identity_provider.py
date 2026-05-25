"""Default identity provider helper tests (Entra-primary post Phase 0.2)."""
from __future__ import annotations

import pytest

from aqp_platform_core.auth import (
    default_identity_provider_alias,
    is_entra_primary,
)


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AQP_AUTH_PROVIDER", raising=False)
    monkeypatch.delenv("AQP_CP_AUTH_PROVIDER", raising=False)


def test_default_is_entra() -> None:
    assert default_identity_provider_alias() == "msal_entra"
    assert is_entra_primary() is True


def test_entra_aliases_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AQP_AUTH_PROVIDER", "entra")
    assert default_identity_provider_alias() == "msal_entra"
    monkeypatch.setenv("AQP_AUTH_PROVIDER", "msal")
    assert default_identity_provider_alias() == "msal_entra"
    monkeypatch.setenv("AQP_AUTH_PROVIDER", "azure_ad")
    assert default_identity_provider_alias() == "msal_entra"


def test_explicit_auth0_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AQP_AUTH_PROVIDER", "auth0")
    assert default_identity_provider_alias() == "auth0"
    assert is_entra_primary() is False


def test_cp_override_wins_when_aqp_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AQP_CP_AUTH_PROVIDER", "auth0")
    assert default_identity_provider_alias() == "auth0"
