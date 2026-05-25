"""Uniform credential resolution for AQP services.

The :class:`CredentialResolver` is the single entry-point every AQP
service uses to look up its outbound credentials. This is the seam that
fixes the "bootstrap-not-applied" class of bug — the canonical example
being Polaris / Iceberg, where :mod:`aqp.services.iceberg_bootstrap`
mints a runtime principal and persists it to disk, but historically
:mod:`aqp.services.polaris_client` and
:mod:`aqp.data.iceberg_catalog` continued to read the static
``settings.polaris_client_*`` / ``settings.iceberg_rest_credential``
seed.

Resolution order (first match wins):

1. **M2M** (Milestone 3, registered later): a fresh service-to-service
   token minted by :class:`aqp.auth.m2m.M2MTokenIssuer`. Disabled by
   default; activates only when ``settings.auth_m2m_enabled`` is true.
2. **File**: bootstrap-minted credentials persisted under
   ``settings.bootstrap_state_dir`` (e.g.
   ``data/bootstrap/polaris-principal.json``).
3. **Env**: the static ``settings.*`` seed values (compose / .env
   defaults). Always available; the safety net.

Concrete stores subclass :class:`SecretStore` and self-register via the
:class:`SecretStoreMeta` metaclass — modeled on
:class:`aqp.rl.core.base.RLComponentMeta` so the registry layer sees
secret stores the same way it sees RL components.

Public surface::

    from aqp.credentials import (
        CredentialKey,
        CredentialResolver,
        SecretStore,
        get_resolver,
    )

    creds = get_resolver().resolve(
        CredentialKey("polaris", "oauth"),
        default={"client_id": "root", "client_secret": "s3cr3t"},
    )

The resolver is a process-wide singleton. Tests that need a fresh
state call :func:`reset_resolver` to drop the cache.
"""
from __future__ import annotations

from aqp.credentials.protocol import (
    Credential,
    CredentialKey,
    CredentialNotFoundError,
    SecretStore,
    SecretStoreMeta,
)
from aqp.credentials.resolver import (
    CredentialResolver,
    get_resolver,
    register_store,
    reset_resolver,
)
from aqp.credentials.datahub import (
    DATAHUB_KEY,
    get_datahub_credential,
    get_datahub_env,
    get_datahub_gms_url,
    get_datahub_token,
)

__all__ = [
    "Credential",
    "CredentialKey",
    "CredentialNotFoundError",
    "CredentialResolver",
    "DATAHUB_KEY",
    "SecretStore",
    "SecretStoreMeta",
    "get_datahub_credential",
    "get_datahub_env",
    "get_datahub_gms_url",
    "get_datahub_token",
    "get_resolver",
    "register_store",
    "reset_resolver",
]
