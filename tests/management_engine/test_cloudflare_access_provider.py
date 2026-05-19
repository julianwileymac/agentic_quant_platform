"""Tests for `aqp.auth.providers.cloudflare_access.CloudflareAccessProvider`.

The provider validates `Cf-Access-Jwt-Assertion` headers against a
team JWKS. We stub the JWKS fetch + sign a synthetic JWT with
PyJWT so the test is fully hermetic.
"""
from __future__ import annotations

import json
import time
from typing import Any

import pytest


def _ensure_pyjwt() -> None:
    try:
        import jwt  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        pytest.skip("PyJWT not installed in this environment")


def _generate_rs256_keypair_and_jwk() -> tuple[Any, Any, dict[str, Any]]:
    """Generate a one-off RSA keypair + the matching JWK dict for tests."""
    _ensure_pyjwt()
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from jwt.algorithms import RSAAlgorithm  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("cryptography or PyJWT[crypto] not installed")

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    jwk["kid"] = "test-kid-1"
    jwk["alg"] = "RS256"
    jwk["use"] = "sig"
    return private_pem, public_pem, jwk


def _sign_token(*, private_pem: bytes, audience: str, issuer: str, kid: str = "test-kid-1") -> str:
    import jwt  # type: ignore[import-not-found]

    payload = {
        "iss": issuer,
        "aud": audience,
        "iat": int(time.time()) - 5,
        "exp": int(time.time()) + 300,
        "sub": "user-1",
        "email": "user@example.com",
    }
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": kid})


def test_extract_returns_none_when_header_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.auth.providers.cloudflare_access import extract_cloudflare_access_claims

    class _Req:
        headers = {}

    assert extract_cloudflare_access_claims(_Req()) is None


def test_extract_returns_none_when_provider_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AQP_CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("AQP_CF_ACCESS_AUD", raising=False)
    from aqp.auth.providers.cloudflare_access import extract_cloudflare_access_claims

    class _Req:
        headers = {"cf-access-jwt-assertion": "anything"}

    assert extract_cloudflare_access_claims(_Req()) is None


def test_valid_jwt_returns_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_pyjwt()
    private_pem, _public_pem, jwk = _generate_rs256_keypair_and_jwk()
    team = "test-team"
    audience = "test-aud-1234567890"
    issuer = f"https://{team}.cloudflareaccess.com"

    monkeypatch.setenv("AQP_CF_ACCESS_TEAM_DOMAIN", team)
    monkeypatch.setenv("AQP_CF_ACCESS_AUD", audience)

    from aqp.auth.providers import cloudflare_access as cf_access

    # Reset the JWKS cache, then patch the fetch with our synthetic key set.
    cf_access._JWKS_CACHE.clear()
    monkeypatch.setattr(
        cf_access,
        "_fetch_jwks",
        lambda _team: {"keys": [jwk]},
    )

    token = _sign_token(
        private_pem=private_pem, audience=audience, issuer=issuer
    )

    class _Req:
        headers = {"cf-access-jwt-assertion": token}

    claims = cf_access.extract_cloudflare_access_claims(_Req())
    assert claims is not None
    assert claims["aud"] == audience
    assert claims["iss"] == issuer
    assert claims["sub"] == "user-1"
    assert claims["email"] == "user@example.com"


def test_invalid_signature_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_pyjwt()
    private_pem, _public_pem, jwk = _generate_rs256_keypair_and_jwk()
    other_private_pem, _other_public_pem, _other_jwk = _generate_rs256_keypair_and_jwk()
    team = "test-team"
    audience = "test-aud"
    issuer = f"https://{team}.cloudflareaccess.com"

    monkeypatch.setenv("AQP_CF_ACCESS_TEAM_DOMAIN", team)
    monkeypatch.setenv("AQP_CF_ACCESS_AUD", audience)

    from aqp.auth.providers import cloudflare_access as cf_access

    cf_access._JWKS_CACHE.clear()
    monkeypatch.setattr(
        cf_access,
        "_fetch_jwks",
        lambda _team: {"keys": [jwk]},  # advertised key is from THIS keypair
    )

    # Sign with the OTHER private key so the advertised JWK can't verify.
    token = _sign_token(
        private_pem=other_private_pem,
        audience=audience,
        issuer=issuer,
    )

    class _Req:
        headers = {"cf-access-jwt-assertion": token}

    # Provider returns None on signature failure (logged, never raised).
    assert cf_access.extract_cloudflare_access_claims(_Req()) is None
