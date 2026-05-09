"""Concrete :class:`aqp.credentials.SecretStore` implementations.

Importing the package registers every concrete store so
:func:`aqp.credentials.get_resolver` can enumerate them via
``list_by_kind("secret_store")``.

The :class:`aqp.credentials.m2m_store.M2MStore` adapter (Milestone 3)
plugs in front of :class:`FileSecretStore` so a configured M2M issuer
takes priority over the bootstrap-minted file payload.
"""
from __future__ import annotations

from aqp.credentials.stores.env_store import EnvSecretStore
from aqp.credentials.stores.file_store import FileSecretStore

__all__ = [
    "EnvSecretStore",
    "FileSecretStore",
]
