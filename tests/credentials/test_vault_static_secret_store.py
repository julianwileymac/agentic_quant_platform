"""Tests for :mod:`aqp.credentials.stores.vault_static_secret_store` (Phase 4 §7.6)."""
from __future__ import annotations

from pathlib import Path

import pytest

from aqp.credentials.protocol import CredentialKey
from aqp.credentials.stores.vault_static_secret_store import (
    PRIORITY_VAULT_STATIC,
    VaultStaticSecretStore,
)


def test_priority_constant() -> None:
    """VaultStaticSecretStore beats AppRole Vault (20) but loses to M2M (10)."""
    assert PRIORITY_VAULT_STATIC == 15
    assert VaultStaticSecretStore.store_priority == PRIORITY_VAULT_STATIC


def test_returns_none_when_mount_dir_missing(tmp_path: Path) -> None:
    """An unset / missing mount dir means 'no opinion'."""
    store = VaultStaticSecretStore(mount_dir=str(tmp_path / "absent"))
    assert store.get(CredentialKey(service="postgres", purpose="dsn")) is None


def test_reads_dot_separated_directory_layout(tmp_path: Path) -> None:
    """The conventional ``<service>.<purpose>`` directory layout works."""
    directory = tmp_path / "postgres.dsn"
    directory.mkdir()
    (directory / "host").write_text("db.example.internal\n")
    (directory / "port").write_text("5432\n")
    (directory / "password").write_text("hunter2")
    store = VaultStaticSecretStore(mount_dir=str(tmp_path))
    credential = store.get(CredentialKey(service="postgres", purpose="dsn"))
    assert credential is not None
    assert credential.fields == {
        "host": "db.example.internal",
        "port": "5432",
        "password": "hunter2",
    }
    assert credential.source.startswith("vault_static_secret:")


def test_reads_slash_separated_directory_layout(tmp_path: Path) -> None:
    """The alternative ``<service>/<purpose>`` layout also works."""
    directory = tmp_path / "postgres" / "dsn"
    directory.mkdir(parents=True)
    (directory / "username").write_text("aqp")
    store = VaultStaticSecretStore(mount_dir=str(tmp_path))
    credential = store.get(CredentialKey(service="postgres", purpose="dsn"))
    assert credential is not None
    assert credential.fields == {"username": "aqp"}


def test_skips_kubernetes_atomic_marker_files(tmp_path: Path) -> None:
    """Kubernetes projected-secret atomic-write markers (``..*``) are skipped."""
    directory = tmp_path / "minio.sts"
    directory.mkdir()
    (directory / "access_key").write_text("AKIA")
    (directory / "..data").write_text("internal-projection-marker")
    (directory / ".hidden").write_text("ignored")
    store = VaultStaticSecretStore(mount_dir=str(tmp_path))
    credential = store.get(CredentialKey(service="minio", purpose="sts"))
    assert credential is not None
    assert set(credential.fields) == {"access_key"}


def test_empty_directory_returns_none(tmp_path: Path) -> None:
    directory = tmp_path / "alpaca.user_oauth"
    directory.mkdir()
    store = VaultStaticSecretStore(mount_dir=str(tmp_path))
    assert store.get(CredentialKey(service="alpaca", purpose="user_oauth")) is None


def test_cached_negatives_dont_re_read(tmp_path: Path) -> None:
    """When a key is missing, the cache short-circuits the next call."""
    store = VaultStaticSecretStore(mount_dir=str(tmp_path), cache_ttl_seconds=60.0)
    assert store.get(CredentialKey(service="missing", purpose="x")) is None
    # Create the directory after the negative cache landed.
    d = tmp_path / "missing.x"
    d.mkdir()
    (d / "value").write_text("present")
    # Still returns None until the cache expires (cache_ttl_seconds=60).
    assert store.get(CredentialKey(service="missing", purpose="x")) is None


def test_describe_includes_mount_dir(tmp_path: Path) -> None:
    store = VaultStaticSecretStore(mount_dir=str(tmp_path))
    summary = store.describe()
    assert summary["kind"] == "vault_static_secret"
    assert summary["priority"] == 15
    assert summary["mount_dir"] == str(tmp_path)


def test_env_override_picks_up_mount_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``AQP_VAULT_STATIC_MOUNT_DIR`` overrides the default when constructor mount is empty."""
    monkeypatch.setenv("AQP_VAULT_STATIC_MOUNT_DIR", str(tmp_path))
    directory = tmp_path / "redis.url"
    directory.mkdir()
    (directory / "url").write_text("redis://aqp-cell-redis:6379/0")
    store = VaultStaticSecretStore()  # no explicit mount_dir
    credential = store.get(CredentialKey(service="redis", purpose="url"))
    assert credential is not None
    assert credential.fields == {"url": "redis://aqp-cell-redis:6379/0"}


def test_strips_trailing_newline(tmp_path: Path) -> None:
    """Files written by VSO end with a trailing newline; the store strips it."""
    directory = tmp_path / "spiffe.bundle"
    directory.mkdir()
    (directory / "trust-domain.pem").write_text("-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----\n")
    store = VaultStaticSecretStore(mount_dir=str(tmp_path))
    credential = store.get(CredentialKey(service="spiffe", purpose="bundle"))
    assert credential is not None
    value = credential.fields["trust-domain.pem"]
    assert not value.endswith("\n")
    assert value.endswith("-----END CERTIFICATE-----")
