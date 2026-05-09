"""PKCE helpers (RFC 7636) for the AQP OIDC login flow.

Ported from
``inspiration/auth0-server-python-main/src/auth0_server_python/utils/helpers.py::PKCE``
(MIT, Copyright Auth0, Inc.) and trimmed to the surface the AQP login
client needs: random verifier + S256 challenge derivation.

Public surface::

    from aqp.auth.pkce import generate_code_verifier, generate_code_challenge
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import string

# Verifier length per RFC 7636 § 4.1: 43–128 chars from the unreserved
# alphabet. 64 matches the upstream default and keeps tokens short.
_DEFAULT_VERIFIER_LENGTH = 64
_ALPHABET = string.ascii_letters + string.digits + "-._~"


def generate_random_string(length: int = _DEFAULT_VERIFIER_LENGTH) -> str:
    """Return a cryptographically secure random string of ``length``."""
    if length < 43 or length > 128:
        raise ValueError(
            "PKCE code verifier length must be 43..128 (RFC 7636); "
            f"got {length}"
        )
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def generate_code_verifier(length: int = _DEFAULT_VERIFIER_LENGTH) -> str:
    """Return a PKCE code verifier (URL-safe random string)."""
    return generate_random_string(length)


def generate_code_challenge(code_verifier: str) -> str:
    """Return the S256 PKCE challenge for ``code_verifier``."""
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


__all__ = [
    "generate_code_challenge",
    "generate_code_verifier",
    "generate_random_string",
]
