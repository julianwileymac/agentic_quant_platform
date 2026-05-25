"""DataHub credential accessor — Rule 26 entry point.

All non-credentials code that needs a DataHub GMS URL or token MUST go
through :func:`get_datahub_credential` (or the convenience wrappers
:func:`get_datahub_token` / :func:`get_datahub_gms_url`). Direct reads
of ``settings.bootstrap_datahub_token`` are forbidden by
``scripts/ci/check_credential_resolver.py``.

The helper resolves the standard ``CredentialKey("datahub",
"default")`` through the active :class:`CredentialResolver` chain, so
M2M / Vault / file stores can override the bootstrap env value without
any caller-side change.
"""
from __future__ import annotations

from aqp.credentials.protocol import Credential, CredentialKey
from aqp.credentials.resolver import get_resolver

DATAHUB_KEY = CredentialKey(service="datahub", purpose="default")


def get_datahub_credential(*, required: bool = False) -> Credential:
    """Resolve the active DataHub credential bundle.

    Returns a :class:`Credential` whose ``fields`` contain ``gms_url``,
    ``token``, and ``env``. Each is a (possibly empty) string. Pass
    ``required=True`` to raise :class:`CredentialNotFoundError` when no
    store offers a value (rare — :class:`EnvSecretStore` always returns
    a hit, even if all three fields are empty strings).
    """
    return get_resolver().resolve(DATAHUB_KEY, required=required)


def get_datahub_token(*, default: str = "") -> str:
    """Convenience: resolved DataHub token, or ``default`` when absent."""
    cred = get_datahub_credential()
    return cred.get("token", default) or default


def get_datahub_gms_url(*, default: str = "") -> str:
    """Convenience: resolved DataHub GMS URL, or ``default`` when absent."""
    cred = get_datahub_credential()
    return cred.get("gms_url", default) or default


def get_datahub_env(*, default: str = "PROD") -> str:
    """Convenience: resolved DataHub environment label."""
    cred = get_datahub_credential()
    return cred.get("env", default) or default


__all__ = [
    "DATAHUB_KEY",
    "get_datahub_credential",
    "get_datahub_env",
    "get_datahub_gms_url",
    "get_datahub_token",
]
