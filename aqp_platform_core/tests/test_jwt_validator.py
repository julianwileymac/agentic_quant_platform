"""JWT validator tests — uses respx + python-jose to mint a test JWT.

Covers happy path, audience mismatch, issuer mismatch, expired token,
and JWKS key rotation. No real network calls.
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt
from jose.utils import long_to_base64

from aqp_platform_core.auth import (
    JwtValidationError,
    JwtValidator,
    JwtValidatorConfig,
)

ISSUER = "https://test-tenant.us.auth0.com/"
AUDIENCE = "https://api.aqp.internal/manage"
JWKS_URL = "https://test-tenant.us.auth0.com/.well-known/jwks.json"


@pytest.fixture
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks_entry(key: rsa.RSAPrivateKey, *, kid: str = "test-kid-1") -> dict[str, Any]:
    numbers = key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": long_to_base64(numbers.n).decode("ascii"),
        "e": long_to_base64(numbers.e).decode("ascii"),
    }


def _mint_token(
    key: rsa.RSAPrivateKey,
    *,
    kid: str = "test-kid-1",
    audience: str = AUDIENCE,
    issuer: str = ISSUER,
    expires_in: int = 300,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": "auth0|123",
        "iat": now,
        "exp": now + expires_in,
        "scope": "read:infrastructure manage:agents",
    }
    if extra_claims:
        claims.update(extra_claims)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def jwks_route(rsa_key: rsa.RSAPrivateKey):
    with respx.mock(assert_all_called=False) as router:
        route = router.get(JWKS_URL).mock(
            return_value=httpx.Response(
                200,
                json={"keys": [_jwks_entry(rsa_key)]},
            )
        )
        yield route


async def test_valid_token_returns_payload(
    rsa_key: rsa.RSAPrivateKey,
    jwks_route,
) -> None:
    validator = JwtValidator(
        JwtValidatorConfig(issuer=ISSUER, audience=AUDIENCE)
    )
    token = _mint_token(rsa_key)
    payload = await validator.validate(token)
    assert payload["sub"] == "auth0|123"
    assert "manage:agents" in payload["scope"]
    await validator.close()


async def test_wrong_audience_rejected(
    rsa_key: rsa.RSAPrivateKey,
    jwks_route,
) -> None:
    validator = JwtValidator(
        JwtValidatorConfig(issuer=ISSUER, audience=AUDIENCE)
    )
    token = _mint_token(rsa_key, audience="https://other-api/")
    with pytest.raises(JwtValidationError) as exc_info:
        await validator.validate(token)
    assert exc_info.value.code in {"wrong_audience", "invalid_claims"}
    await validator.close()


async def test_wrong_issuer_rejected(
    rsa_key: rsa.RSAPrivateKey,
    jwks_route,
) -> None:
    validator = JwtValidator(
        JwtValidatorConfig(issuer=ISSUER, audience=AUDIENCE)
    )
    token = _mint_token(rsa_key, issuer="https://other-tenant/")
    with pytest.raises(JwtValidationError) as exc_info:
        await validator.validate(token)
    assert exc_info.value.code in {"wrong_issuer", "invalid_claims"}
    await validator.close()


async def test_expired_token_rejected(
    rsa_key: rsa.RSAPrivateKey,
    jwks_route,
) -> None:
    validator = JwtValidator(
        JwtValidatorConfig(issuer=ISSUER, audience=AUDIENCE, leeway_seconds=0)
    )
    token = _mint_token(rsa_key, expires_in=-60)
    with pytest.raises(JwtValidationError) as exc_info:
        await validator.validate(token)
    assert exc_info.value.code == "expired_token"
    await validator.close()


async def test_missing_kid_rejected(
    rsa_key: rsa.RSAPrivateKey,
    jwks_route,
) -> None:
    validator = JwtValidator(
        JwtValidatorConfig(issuer=ISSUER, audience=AUDIENCE)
    )
    # Mint a token with no kid header by encoding manually.
    pem = rsa_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    now = int(time.time())
    token = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "x", "iat": now, "exp": now + 60},
        pem,
        algorithm="RS256",
    )
    with pytest.raises(JwtValidationError) as exc_info:
        await validator.validate(token)
    assert exc_info.value.code == "invalid_token"
    await validator.close()


async def test_unknown_kid_triggers_refresh_and_then_fails(
    rsa_key: rsa.RSAPrivateKey,
) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(JWKS_URL).mock(
            return_value=httpx.Response(
                200, json={"keys": [_jwks_entry(rsa_key, kid="other-kid")]}
            )
        )
        validator = JwtValidator(
            JwtValidatorConfig(issuer=ISSUER, audience=AUDIENCE)
        )
        token = _mint_token(rsa_key, kid="missing-kid")
        with pytest.raises(JwtValidationError) as exc_info:
            await validator.validate(token)
        assert exc_info.value.code == "no_matching_key"
        await validator.close()


def test_decode_unverified_returns_payload(
    rsa_key: rsa.RSAPrivateKey,
) -> None:
    token = _mint_token(rsa_key, extra_claims={"https://aqp.internal/org_id": "org-1"})
    payload = JwtValidator.decode_unverified(token)
    assert payload["sub"] == "auth0|123"
    assert payload["https://aqp.internal/org_id"] == "org-1"


def test_decode_unverified_rejects_malformed() -> None:
    with pytest.raises(JwtValidationError, match="malformed"):
        JwtValidator.decode_unverified("not-a-jwt")
