"""JWE encrypt / decrypt helpers for cookie-friendly session payloads.

Ported from
``inspiration/auth0-server-python-main/src/auth0_server_python/encryption/encrypt.py``
(MIT, Copyright Auth0, Inc.). Two intentional changes from upstream:

1. The HKDF ``info`` constant is renamed from
   ``b"Auth0 Generated Encryption"`` to ``b"AQP Identity Encryption"``.
   We have no legacy cookies to preserve, and a neutral label avoids
   leaking vendor identity in inspectable JWEs.
2. The public surface is two functions
   (:func:`encrypt_payload` / :func:`decrypt_payload`) instead of
   ``encrypt`` / ``decrypt`` — the longer names compose better with the
   :class:`aqp.auth.session.StateStore` API and make grep less noisy.

Algorithm: ``alg=dir``, ``enc=A256CBC-HS512``, key derived via HKDF-SHA256
with a per-identifier ``salt`` (e.g. the user/session id) so leaking one
session key does not reveal others.
"""
from __future__ import annotations

import json
from typing import Any

# Constants chosen to match the upstream defaults so cookies issued by
# either implementation could in principle be cross-decoded if the salt
# + secret + ENCRYPTION_INFO matched. We diverge intentionally on
# ENCRYPTION_INFO — see module docstring.
_ENC = "A256CBC-HS512"
_ALG = "dir"
_BYTE_LENGTH = 64
_ENCRYPTION_INFO = b"AQP Identity Encryption"


def _derive_key(secret: bytes, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_BYTE_LENGTH,
        salt=salt,
        info=_ENCRYPTION_INFO,
    )
    return hkdf.derive(secret)


def encrypt_payload(payload: dict[str, Any], secret: str, salt: str) -> str:
    """Encrypt ``payload`` to a compact-serialised JWE string.

    Raises:
        ImportError: ``jwcrypto`` is not installed.
        ValueError: ``secret`` or ``salt`` is empty.
    """
    if not secret:
        raise ValueError("encrypt_payload requires a non-empty secret")
    if not salt:
        raise ValueError("encrypt_payload requires a non-empty salt")

    from jwcrypto import jwe, jwk
    from jwcrypto.common import base64url_encode

    key_bytes = _derive_key(secret.encode("utf-8"), salt.encode("utf-8"))
    key = jwk.JWK(k=base64url_encode(key_bytes), kty="oct")
    token = jwe.JWE(
        json.dumps(payload),
        protected={"alg": _ALG, "enc": _ENC},
    )
    token.add_recipient(key)
    return token.serialize(compact=True)


def decrypt_payload(token: str, secret: str, salt: str) -> dict[str, Any]:
    """Decrypt a compact JWE produced by :func:`encrypt_payload`."""
    if not token:
        raise ValueError("decrypt_payload requires a non-empty token")

    from jwcrypto import jwe, jwk
    from jwcrypto.common import base64url_encode

    key_bytes = _derive_key(secret.encode("utf-8"), salt.encode("utf-8"))
    key = jwk.JWK(k=base64url_encode(key_bytes), kty="oct")
    parsed = jwe.JWE()
    parsed.deserialize(token)
    parsed.decrypt(key)
    return json.loads(parsed.payload.decode("utf-8"))


__all__ = ["decrypt_payload", "encrypt_payload"]
