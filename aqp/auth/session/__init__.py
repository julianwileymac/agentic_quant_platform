"""Session storage primitives for the AQP identity layer.

The package provides:

- :mod:`aqp.auth.session.crypto` — JWE encrypt / decrypt for cookie
  payloads (ported from auth0-server-python).
- :class:`StateStore` ABC mirroring the upstream
  ``auth0_server_python.store.abstract.StateStore`` so concrete stores
  can be swapped for tests / different deployment shapes.
- :class:`StateData` / :class:`TransactionData` typed payloads.

Concrete stores (:class:`EncryptedCookieStore`, :class:`RedisStateStore`)
are added in Milestone 3 — this module only ships the contracts so the
provider abstraction (Milestone 2) can compile against them.
"""
from __future__ import annotations

from aqp.auth.session.crypto import decrypt_payload, encrypt_payload
from aqp.auth.session.protocol import (
    StateData,
    StateStore,
    TokenSet,
    TransactionData,
    TransactionStore,
)
from aqp.auth.session.stores import (
    EncryptedCookieStateStore,
    EncryptedCookieTransactionStore,
    RedisStateStore,
    RedisTransactionStore,
    session_payload_from_tokens,
)

__all__ = [
    "EncryptedCookieStateStore",
    "EncryptedCookieTransactionStore",
    "RedisStateStore",
    "RedisTransactionStore",
    "StateData",
    "StateStore",
    "TokenSet",
    "TransactionData",
    "TransactionStore",
    "decrypt_payload",
    "encrypt_payload",
    "session_payload_from_tokens",
]
