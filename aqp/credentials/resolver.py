"""Process-wide :class:`CredentialResolver` singleton.

Holds an ordered chain of :class:`SecretStore` instances and routes
:class:`CredentialKey` lookups through them. Order is by
``store_priority`` (lower wins), so an :class:`M2MStore` registered at
:data:`PRIORITY_M2M` (10) supersedes :class:`FileSecretStore` (50)
which supersedes :class:`EnvSecretStore` (100).

The resolver is lazy and singleton-y: :func:`get_resolver` constructs
the default chain (``EnvSecretStore`` + ``FileSecretStore``) on first
call. Tests reset state via :func:`reset_resolver`.

Adding new stores at runtime (e.g. when M2M is wired in M3) goes
through :func:`register_store` so the singleton picks them up without
hard-importing every concrete store at module load time.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from aqp.credentials.protocol import (
    Credential,
    CredentialKey,
    CredentialNotFoundError,
    SecretStore,
)

logger = logging.getLogger(__name__)


class CredentialResolver:
    """Ordered :class:`SecretStore` chain.

    Construct directly for tests; production code should use
    :func:`get_resolver` to share the singleton.
    """

    def __init__(self, stores: list[SecretStore] | None = None) -> None:
        self._lock = threading.RLock()
        self._stores: list[SecretStore] = []
        for store in stores or []:
            self.add_store(store)

    def add_store(self, store: SecretStore) -> None:
        """Insert ``store`` into the chain, maintaining priority order."""
        with self._lock:
            for existing in self._stores:
                if type(existing) is type(store):
                    return
            self._stores.append(store)
            self._stores.sort(key=lambda s: int(getattr(s, "store_priority", 100)))

    def remove_store(self, store_kind: str) -> int:
        """Remove every store whose ``store_kind`` matches ``store_kind``.

        Returns the number of stores removed. Used by tests and the M2M
        toggle (M3) when the operator disables federated identity.
        """
        with self._lock:
            before = len(self._stores)
            self._stores = [s for s in self._stores if s.store_kind != store_kind]
            return before - len(self._stores)

    def stores(self) -> list[SecretStore]:
        with self._lock:
            return list(self._stores)

    def resolve(
        self,
        key: CredentialKey,
        *,
        default: dict[str, str] | None = None,
        required: bool = False,
    ) -> Credential:
        """Resolve ``key`` through the registered chain.

        Returns the first non-empty hit, with fields filled in from
        ``default`` for any keys missing from the hit. When no store
        offers a value:

        - ``required=False`` (default): returns a :class:`Credential`
          built from ``default`` (or empty fields when ``default`` is
          ``None``).
        - ``required=True``: raises :class:`CredentialNotFoundError`.
        """
        with self._lock:
            chain = list(self._stores)

        for store in chain:
            try:
                hit = store.get(key)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "credential store %s raised on key %s: %s",
                    store.store_kind,
                    key,
                    exc,
                    exc_info=True,
                )
                continue
            if hit is None:
                continue
            if not hit.fields:
                # Treat empty payloads as a "no value" hit so env
                # defaults still flow through.
                continue
            return hit.merge_default(default)

        if required:
            raise CredentialNotFoundError(str(key))
        return Credential(
            fields={k: str(v) for k, v in (default or {}).items() if v not in (None, "")},
            source="default",
        )

    def describe(self) -> dict[str, Any]:
        return {"stores": [store.describe() for store in self.stores()]}


# ---------------------------------------------------------------------------
# Singleton + helpers
# ---------------------------------------------------------------------------


_RESOLVER: CredentialResolver | None = None
_RESOLVER_LOCK = threading.Lock()


def _build_default_resolver() -> CredentialResolver:
    """Build the default chain.

    Baseline: ``env`` + ``file`` (always present, no external deps).

    Additive: when ``AQP_DEFAULT_CLOUD_PROVIDER`` is set and the
    matching cloud SDK is installed, the matching cloud SecretStore is
    inserted at priority 30 (between m2m=10 and file=50). When
    ``AQP_VAULT_ADDR`` is set and ``hvac`` is installed, the Vault
    store is inserted at priority 15 (above all cloud stores).
    """
    from aqp.credentials.stores.env_store import EnvSecretStore
    from aqp.credentials.stores.file_store import FileSecretStore

    resolver = CredentialResolver()
    resolver.add_store(EnvSecretStore())
    resolver.add_store(FileSecretStore())

    # Optional Vault layer (priority 20 — above all cloud stores).
    try:
        from aqp.config import settings

        if (str(getattr(settings, "vault_addr", "") or "")).strip():
            from aqp.credentials.stores import HashicorpVaultSecretStore

            if HashicorpVaultSecretStore is not None:
                resolver.add_store(HashicorpVaultSecretStore())
    except Exception:  # noqa: BLE001
        logger.debug("HashicorpVaultSecretStore auto-registration failed", exc_info=True)

    # Optional cloud layer (selected by AQP_DEFAULT_CLOUD_PROVIDER).
    try:
        from aqp.config import settings

        cloud = (
            str(getattr(settings, "default_cloud_provider", "") or "")
            .strip()
            .lower()
        )
    except Exception:
        cloud = ""

    if cloud == "azure":
        try:
            from aqp.credentials.stores import AzureKeyVaultSecretStore

            if AzureKeyVaultSecretStore is not None:
                resolver.add_store(AzureKeyVaultSecretStore())
        except Exception:  # noqa: BLE001
            logger.debug(
                "AzureKeyVaultSecretStore auto-registration failed", exc_info=True
            )
    elif cloud == "aws":
        try:
            from aqp.credentials.stores import AwsSecretsManagerStore

            if AwsSecretsManagerStore is not None:
                resolver.add_store(AwsSecretsManagerStore())
        except Exception:  # noqa: BLE001
            logger.debug(
                "AwsSecretsManagerStore auto-registration failed", exc_info=True
            )
    elif cloud == "gcp":
        try:
            from aqp.credentials.stores import GcpSecretManagerStore

            if GcpSecretManagerStore is not None:
                resolver.add_store(GcpSecretManagerStore())
        except Exception:  # noqa: BLE001
            logger.debug(
                "GcpSecretManagerStore auto-registration failed", exc_info=True
            )
    return resolver


def get_resolver() -> CredentialResolver:
    """Return the process-wide resolver, constructing on first access."""
    global _RESOLVER
    if _RESOLVER is None:
        with _RESOLVER_LOCK:
            if _RESOLVER is None:
                _RESOLVER = _build_default_resolver()
    return _RESOLVER


def register_store(store: SecretStore) -> None:
    """Add ``store`` to the singleton resolver."""
    get_resolver().add_store(store)


def reset_resolver(stores: list[SecretStore] | None = None) -> None:
    """Drop the singleton (or replace it with an explicit chain).

    Tests use this to start each case from a known state. Production
    code should not call this — credentials should change via store
    semantics (file refresh, M2M toggle), not by re-building the
    resolver.
    """
    global _RESOLVER
    with _RESOLVER_LOCK:
        _RESOLVER = CredentialResolver(stores) if stores is not None else None


__all__ = [
    "CredentialResolver",
    "get_resolver",
    "register_store",
    "reset_resolver",
]
