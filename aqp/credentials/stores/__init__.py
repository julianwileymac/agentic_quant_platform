"""Concrete :class:`aqp.credentials.SecretStore` implementations.

Importing the package registers every concrete store so
:func:`aqp.credentials.get_resolver` can enumerate them via
``list_by_kind("secret_store")``.

Cloud stores (Azure Key Vault / AWS Secrets Manager / GCP Secret
Manager) and HashiCorp Vault are imported in try/except so the AQP
package keeps installable without every cloud SDK. Each store
gracefully returns ``None`` for every key when its SDK is missing.
"""
from __future__ import annotations

from aqp.credentials.stores.env_store import EnvSecretStore
from aqp.credentials.stores.file_store import FileSecretStore

try:  # pragma: no cover - dep guard
    from aqp.credentials.stores.azure_keyvault_store import (  # noqa: F401
        AzureKeyVaultSecretStore,
    )
except Exception:  # noqa: BLE001
    AzureKeyVaultSecretStore = None  # type: ignore[assignment]

try:  # pragma: no cover - dep guard
    from aqp.credentials.stores.aws_secretsmanager_store import (  # noqa: F401
        AwsSecretsManagerStore,
    )
except Exception:  # noqa: BLE001
    AwsSecretsManagerStore = None  # type: ignore[assignment]

try:  # pragma: no cover - dep guard
    from aqp.credentials.stores.gcp_secretmanager_store import (  # noqa: F401
        GcpSecretManagerStore,
    )
except Exception:  # noqa: BLE001
    GcpSecretManagerStore = None  # type: ignore[assignment]

try:  # pragma: no cover - dep guard
    from aqp.credentials.stores.hashicorp_vault_store import (  # noqa: F401
        HashicorpVaultSecretStore,
    )
except Exception:  # noqa: BLE001
    HashicorpVaultSecretStore = None  # type: ignore[assignment]


__all__ = [
    "AwsSecretsManagerStore",
    "AzureKeyVaultSecretStore",
    "EnvSecretStore",
    "FileSecretStore",
    "GcpSecretManagerStore",
    "HashicorpVaultSecretStore",
]
