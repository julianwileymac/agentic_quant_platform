"""Credential protocol — keys, values, and the abstract resolver chain.

Pure ABC + value types — no auto-registration. The ``aqp/`` version
inherits from this and adds the ``aqp.core.registry`` integration;
the control plane uses these directly.
"""
from __future__ import annotations

from aqp_platform_core.credentials.protocol import (
    PRIORITY_ENV,
    PRIORITY_FILE,
    PRIORITY_M2M,
    Credential,
    CredentialKey,
    CredentialNotFoundError,
    SecretStore,
)

__all__ = [
    "PRIORITY_ENV",
    "PRIORITY_FILE",
    "PRIORITY_M2M",
    "Credential",
    "CredentialKey",
    "CredentialNotFoundError",
    "SecretStore",
]
