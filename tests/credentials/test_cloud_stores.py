"""Smoke tests for the four cloud SecretStore implementations.

Each store degrades to a no-op (returns ``None`` for every key) when
its optional cloud SDK isn't installed — these tests confirm the
graceful-degradation contract without requiring the cloud SDKs.
"""
from __future__ import annotations

import importlib.util

import pytest

from aqp.credentials.protocol import CredentialKey


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def test_azure_keyvault_store_returns_none_without_url():
    from aqp.credentials.stores.azure_keyvault_store import AzureKeyVaultSecretStore

    store = AzureKeyVaultSecretStore(vault_url="")
    assert store.get(CredentialKey("polaris", "oauth")) is None


def test_aws_secretsmanager_store_returns_none_without_boto3(monkeypatch):
    """When boto3 is missing the store cleanly degrades."""
    from aqp.credentials.stores import aws_secretsmanager_store as mod

    # Force boto3 import failure
    monkeypatch.setattr(
        "aqp.credentials.stores.aws_secretsmanager_store.AwsSecretsManagerStore._get_client",
        lambda self: None,
    )
    store = mod.AwsSecretsManagerStore()
    assert store.get(CredentialKey("alpaca", "default")) is None


def test_gcp_secretmanager_store_returns_none_without_project_id():
    from aqp.credentials.stores.gcp_secretmanager_store import GcpSecretManagerStore

    store = GcpSecretManagerStore(project_id="")
    assert store.get(CredentialKey("alpaca", "default")) is None


def test_vault_store_returns_none_without_addr():
    from aqp.credentials.stores.hashicorp_vault_store import (
        HashicorpVaultSecretStore,
    )

    store = HashicorpVaultSecretStore(addr="")
    assert store.get(CredentialKey("polaris", "oauth")) is None


def test_priority_ordering():
    """Cloud stores live at priority 30 (between M2M=10 and File=50)."""
    from aqp.credentials.stores.aws_secretsmanager_store import PRIORITY_AWS_SM
    from aqp.credentials.stores.azure_keyvault_store import PRIORITY_AZURE_KV
    from aqp.credentials.stores.gcp_secretmanager_store import PRIORITY_GCP_SM
    from aqp.credentials.stores.hashicorp_vault_store import PRIORITY_VAULT

    assert PRIORITY_VAULT < PRIORITY_AZURE_KV
    assert PRIORITY_AZURE_KV == PRIORITY_AWS_SM == PRIORITY_GCP_SM
    assert PRIORITY_AZURE_KV == 30
    assert PRIORITY_VAULT == 20


def test_azure_keyvault_key_normalization():
    from aqp.credentials.stores.azure_keyvault_store import _normalize_key

    name = _normalize_key(CredentialKey("polaris", "oauth"))
    assert name == "aqp-polaris-oauth"
    # Underscores + colons collapse to hyphens
    name2 = _normalize_key(CredentialKey("foo.bar:baz", "qux"))
    assert "--" not in name2
    assert name2.startswith("aqp-")


def test_aws_secret_name_uses_slash_separator():
    from aqp.credentials.stores.aws_secretsmanager_store import AwsSecretsManagerStore

    store = AwsSecretsManagerStore(prefix="aqp/")
    assert store._secret_name(CredentialKey("polaris", "oauth")) == "aqp/polaris/oauth"


def test_gcp_secret_id_uses_hyphen_separator():
    from aqp.credentials.stores.gcp_secretmanager_store import _normalize_id

    name = _normalize_id("aqp-", CredentialKey("polaris", "oauth"))
    assert name == "aqp-polaris-oauth"
