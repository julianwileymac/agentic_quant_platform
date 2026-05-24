"""Concrete :class:`ExternalOAuthProvider` implementations.

Importing this package transitively registers every concrete provider
via :class:`ExternalOAuthProviderMeta`.
"""
from __future__ import annotations

from aqp.auth.external_oauth.providers import (  # noqa: F401  (side-effects)
    bloomberg,
    fred,
    generic,
    github,
    refinitiv,
)

__all__: list[str] = []
