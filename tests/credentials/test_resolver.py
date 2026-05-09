"""Tests for :mod:`aqp.credentials`.

Covers:

- The resolver picks the highest-priority store with a non-empty
  payload.
- The :class:`FileSecretStore` reads the bootstrap-persisted JSON and
  takes priority over :class:`EnvSecretStore`.
- Empty hits (e.g. env returning empty fields) fall through to the next
  store.
- ``required=True`` raises when nothing matches.
- :func:`reset_resolver` rebuilds the chain on the next ``get_resolver``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aqp.credentials import (
    CredentialKey,
    CredentialNotFoundError,
    CredentialResolver,
    SecretStore,
    get_resolver,
    register_store,
    reset_resolver,
)
from aqp.credentials.protocol import (
    PRIORITY_ENV,
    PRIORITY_FILE,
    PRIORITY_M2M,
    Credential,
)
from aqp.credentials.stores.env_store import EnvSecretStore
from aqp.credentials.stores.file_store import FileSecretStore


class _StubSettings:
    """Plain object that mimics the AQP ``settings`` surface used by env_store."""

    def __init__(self, **fields):
        self.polaris_client_id = fields.get("polaris_client_id", "root")
        self.polaris_client_secret = fields.get("polaris_client_secret", "s3cr3t")
        self.iceberg_principal_name = fields.get("iceberg_principal_name", "aqp_runtime")
        self.iceberg_rest_credential = fields.get("iceberg_rest_credential", "")
        self.iceberg_rest_token = fields.get("iceberg_rest_token", "")
        self.iceberg_rest_oauth2_server_uri = fields.get(
            "iceberg_rest_oauth2_server_uri", ""
        )
        self.iceberg_rest_scope = fields.get("iceberg_rest_scope", "")
        self.trino_admin_user = fields.get("trino_admin_user", "aqp")
        self.trino_admin_source = fields.get("trino_admin_source", "aqp-test")
        self.s3_access_key = fields.get("s3_access_key", "aqpminio")
        self.s3_secret_key = fields.get("s3_secret_key", "aqpminiosecret")
        self.s3_endpoint_url = fields.get("s3_endpoint_url", "http://minio:9000")
        self.s3_region = fields.get("s3_region", "us-east-1")
        self.neo4j_user = fields.get("neo4j_user", "neo4j")
        self.neo4j_password = fields.get("neo4j_password", "aqpneo4j")
        self.neo4j_uri = fields.get("neo4j_uri", "bolt://localhost:7687")


@pytest.fixture
def stub_settings():
    return _StubSettings()


@pytest.fixture(autouse=True)
def _reset_resolver():
    reset_resolver()
    yield
    reset_resolver()


def test_env_store_returns_polaris_oauth(stub_settings):
    store = EnvSecretStore(settings_obj=stub_settings)
    cred = store.get(CredentialKey("polaris", "oauth"))
    assert cred is not None
    assert cred.source == "env"
    assert cred.get("client_id") == "root"
    assert cred.get("client_secret") == "s3cr3t"
    assert cred.get("principal") == "aqp_runtime"


def test_env_store_unknown_key_returns_none(stub_settings):
    store = EnvSecretStore(settings_obj=stub_settings)
    assert store.get(CredentialKey("does-not-exist", "oauth")) is None


def test_file_store_reads_polaris_principal(tmp_path: Path):
    payload = {
        "client_id": "minted-id",
        "client_secret": "minted-secret",
        "principal": "aqp_runtime",
    }
    (tmp_path / "polaris-principal.json").write_text(json.dumps(payload))
    store = FileSecretStore(base_dir=tmp_path)
    cred = store.get(CredentialKey("polaris", "oauth"))
    assert cred is not None
    assert cred.source == "file"
    assert cred.get("client_id") == "minted-id"
    assert cred.get("client_secret") == "minted-secret"


def test_file_store_returns_none_when_payload_missing(tmp_path: Path):
    store = FileSecretStore(base_dir=tmp_path)
    assert store.get(CredentialKey("polaris", "oauth")) is None


def test_file_store_returns_none_when_secret_blank(tmp_path: Path):
    (tmp_path / "polaris-principal.json").write_text(
        json.dumps({"client_id": "id-only", "client_secret": ""})
    )
    store = FileSecretStore(base_dir=tmp_path)
    assert store.get(CredentialKey("polaris", "oauth")) is None


def test_file_store_polaris_rest_returns_credential_string(tmp_path: Path):
    (tmp_path / "polaris-principal.json").write_text(
        json.dumps({"client_id": "abc", "client_secret": "xyz"})
    )
    store = FileSecretStore(base_dir=tmp_path)
    cred = store.get(CredentialKey("polaris", "rest"))
    assert cred is not None
    assert cred.get("credential") == "abc:xyz"


def test_resolver_priority_order_file_beats_env(tmp_path: Path, stub_settings):
    (tmp_path / "polaris-principal.json").write_text(
        json.dumps({"client_id": "minted", "client_secret": "minted-secret"})
    )
    resolver = CredentialResolver(
        [
            EnvSecretStore(settings_obj=stub_settings),
            FileSecretStore(base_dir=tmp_path),
        ]
    )
    cred = resolver.resolve(CredentialKey("polaris", "oauth"))
    assert cred.source == "file"
    assert cred.get("client_id") == "minted"


def test_resolver_priority_order_m2m_beats_file(tmp_path: Path, stub_settings):
    (tmp_path / "polaris-principal.json").write_text(
        json.dumps({"client_id": "minted", "client_secret": "minted-secret"})
    )

    class _M2MStub(SecretStore):
        store_kind = "m2m"
        store_priority = PRIORITY_M2M

        def get(self, key):
            if key.service == "polaris":
                return Credential(
                    fields={"client_id": "m2m-id", "client_secret": "m2m-secret"},
                    source="m2m",
                    ttl_seconds=900,
                )
            return None

    resolver = CredentialResolver(
        [
            EnvSecretStore(settings_obj=stub_settings),
            FileSecretStore(base_dir=tmp_path),
            _M2MStub(),
        ]
    )
    cred = resolver.resolve(CredentialKey("polaris", "oauth"))
    assert cred.source == "m2m"
    assert cred.get("client_id") == "m2m-id"
    assert cred.ttl_seconds == 900


def test_resolver_falls_through_to_default_when_nothing_resolves():
    resolver = CredentialResolver([])
    cred = resolver.resolve(
        CredentialKey("polaris", "oauth"),
        default={"client_id": "fallback", "client_secret": "fallback-secret"},
    )
    assert cred.source == "default"
    assert cred.get("client_id") == "fallback"


def test_resolver_required_true_raises_on_miss():
    resolver = CredentialResolver([])
    with pytest.raises(CredentialNotFoundError):
        resolver.resolve(CredentialKey("nope", "oauth"), required=True)


def test_resolver_merges_default_into_partial_hit(tmp_path: Path):
    (tmp_path / "polaris-principal.json").write_text(
        json.dumps({"client_id": "abc", "client_secret": "xyz"})
    )
    resolver = CredentialResolver([FileSecretStore(base_dir=tmp_path)])
    cred = resolver.resolve(
        CredentialKey("polaris", "oauth"),
        default={"client_id": "fallback", "audience": "polaris-api"},
    )
    # File hit wins for client_id; default fills missing audience.
    assert cred.get("client_id") == "abc"
    assert cred.get("client_secret") == "xyz"
    assert cred.get("audience") == "polaris-api"


def test_resolver_skips_empty_hits(tmp_path: Path, stub_settings):
    """Env returns an empty Credential for unrelated services; resolver moves on."""
    resolver = CredentialResolver([EnvSecretStore(settings_obj=stub_settings)])
    cred = resolver.resolve(
        CredentialKey("totally-different-service", "anything"),
        default={"x": "y"},
    )
    assert cred.source == "default"
    assert cred.get("x") == "y"


def test_get_resolver_singleton_is_lazy():
    reset_resolver()
    a = get_resolver()
    b = get_resolver()
    assert a is b


def test_reset_resolver_with_explicit_chain(stub_settings):
    reset_resolver([EnvSecretStore(settings_obj=stub_settings)])
    chain = get_resolver().stores()
    assert len(chain) == 1
    assert chain[0].store_kind == "env"


def test_register_store_updates_singleton(tmp_path: Path):
    reset_resolver([])

    class _ExtraStub(SecretStore):
        store_kind = "extra"
        store_priority = 5

        def get(self, key):
            return None

    register_store(_ExtraStub())
    kinds = [s.store_kind for s in get_resolver().stores()]
    assert "extra" in kinds


def test_resolver_describe_returns_chain_metadata(stub_settings):
    resolver = CredentialResolver(
        [EnvSecretStore(settings_obj=stub_settings), FileSecretStore()]
    )
    info = resolver.describe()
    kinds = [entry["kind"] for entry in info["stores"]]
    assert kinds == ["file", "env"] or kinds == ["env", "file"]
    priorities = [entry["priority"] for entry in info["stores"]]
    assert sorted(priorities) == [PRIORITY_FILE, PRIORITY_ENV]
