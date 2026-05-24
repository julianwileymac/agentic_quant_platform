"""Tests for :mod:`aqp.credentials.stores.broker_credential_store` (AGENTS rule 55)."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from aqp.credentials.protocol import CredentialKey
from aqp.credentials.stores.broker_credential_store import (
    BACKEND_AWS_SECRETS_MANAGER,
    BACKEND_HASHICORP_VAULT,
    BACKEND_LOCAL,
    BROKER_PURPOSE,
    BrokerCredentialStore,
)


def _ctx_user(user_id: str | None = "user-1", org_id: str | None = "org-1") -> Any:
    """Build a stub RequestContext that the store reads via the contextvar."""
    ctx = MagicMock()
    ctx.user_id = user_id
    ctx.org_id = org_id
    return ctx


def test_store_returns_none_for_non_broker_purpose() -> None:
    store = BrokerCredentialStore()
    with patch(
        "aqp.credentials.stores.broker_credential_store._current_user_id",
        return_value="user-1",
    ):
        result = store.get(CredentialKey(service="alpaca", purpose="user_oauth"))
    assert result is None


def test_store_returns_none_when_no_user_id_in_context() -> None:
    store = BrokerCredentialStore()
    with patch(
        "aqp.credentials.stores.broker_credential_store._current_user_id",
        return_value=None,
    ):
        result = store.get(CredentialKey(service="alpaca", purpose=BROKER_PURPOSE))
    assert result is None


def test_resolve_backend_falls_back_to_local_when_no_org() -> None:
    """Without an active org context, the store always uses the local backend."""
    from aqp.credentials.stores.broker_credential_store import _resolve_backend_for_user

    with patch(
        "aqp.credentials.stores.broker_credential_store._current_org_id",
        return_value=None,
    ):
        backend = _resolve_backend_for_user("user-1")
    assert backend == BACKEND_LOCAL


def test_resolve_backend_reads_organization_column() -> None:
    """The store reads `Organization.broker_credential_backend` per call."""
    from aqp.credentials.stores.broker_credential_store import _resolve_backend_for_user

    class _FakeOrg:
        broker_credential_backend = BACKEND_HASHICORP_VAULT

    fake_session = MagicMock()
    fake_session.__enter__ = MagicMock(return_value=fake_session)
    fake_session.__exit__ = MagicMock(return_value=False)
    fake_session.query.return_value.filter.return_value.one_or_none.return_value = _FakeOrg()

    with patch(
        "aqp.credentials.stores.broker_credential_store._current_org_id",
        return_value="org-1",
    ), patch("aqp.persistence.db.get_session", return_value=fake_session), patch(
        "aqp.persistence.models_tenancy.Organization", _FakeOrg
    ):
        backend = _resolve_backend_for_user("user-1")
    assert backend == BACKEND_HASHICORP_VAULT


def test_resolve_backend_local_on_db_failure() -> None:
    """A DB blip should NEVER flip the backend to 'unknown' mid-trade."""
    from aqp.credentials.stores.broker_credential_store import _resolve_backend_for_user

    with patch(
        "aqp.credentials.stores.broker_credential_store._current_org_id",
        return_value="org-1",
    ), patch("aqp.persistence.db.get_session", side_effect=RuntimeError("db down")):
        backend = _resolve_backend_for_user("user-1")
    assert backend == BACKEND_LOCAL


def test_store_delegates_to_resolver_chain_for_external_backend() -> None:
    """When the org's backend is hashicorp_vault, the store builds a deterministic
    key + delegates to the regular CredentialResolver chain so the existing
    cloud-KMS stores resolve it."""
    from aqp.credentials.protocol import Credential
    from aqp.credentials.stores.broker_credential_store import _read_external

    fake_resolver = MagicMock()
    fake_resolver.resolve.return_value = Credential(
        fields={"api_key": "vault-stored-key"},
        source="hashicorp_vault",
    )
    with patch(
        "aqp.credentials.stores.broker_credential_store.get_resolver",
        return_value=fake_resolver,
    ):
        result = _read_external(
            backend=BACKEND_HASHICORP_VAULT,
            user_id="user-1",
            provider="alpaca",
            label="primary",
        )
    assert result is not None
    assert result.fields.get("api_key") == "vault-stored-key"
    assert result.source == f"broker:external:{BACKEND_HASHICORP_VAULT}"
    # Verify the resolver was called with the expected key shape.
    fake_resolver.resolve.assert_called_once()
    call_args = fake_resolver.resolve.call_args
    delegated_key = call_args.args[0]
    assert delegated_key.service == "broker:alpaca"
    assert delegated_key.purpose == "user:user-1:primary"


def test_external_lookup_returns_none_when_vault_misses() -> None:
    from aqp.credentials.stores.broker_credential_store import _read_external

    fake_resolver = MagicMock()
    fake_resolver.resolve.return_value = None
    with patch(
        "aqp.credentials.stores.broker_credential_store.get_resolver",
        return_value=fake_resolver,
    ):
        result = _read_external(
            backend=BACKEND_AWS_SECRETS_MANAGER,
            user_id="user-1",
            provider="alpaca",
            label="",
        )
    assert result is None


def test_service_key_supports_provider_and_provider_label_shapes() -> None:
    """The store accepts both 'alpaca' and 'alpaca:primary' as service names."""
    store = BrokerCredentialStore()

    captured: dict[str, str] = {}

    def _capture_local(*, user_id, provider, label):  # noqa: ANN001
        captured["provider"] = provider
        captured["label"] = label
        return None

    with patch(
        "aqp.credentials.stores.broker_credential_store._current_user_id",
        return_value="user-1",
    ), patch(
        "aqp.credentials.stores.broker_credential_store._resolve_backend_for_user",
        return_value=BACKEND_LOCAL,
    ), patch("aqp.credentials.stores.broker_credential_store._read_local", _capture_local):
        store.get(CredentialKey(service="alpaca:primary", purpose=BROKER_PURPOSE))
        assert captured == {"provider": "alpaca", "label": "primary"}
        store.get(CredentialKey(service="alpaca", purpose=BROKER_PURPOSE))
        assert captured == {"provider": "alpaca", "label": ""}
