"""Tests for :mod:`aqp.auth.oidc_client`.

Mocks ``httpx`` so we don't hit the network. Covers:

- Discovery TTL caching.
- JWKS reads pull from the discovery doc.
- ``exchange_code`` posts the right grant + decodes the response.
- ``client_credentials`` posts ``audience`` / ``scope``.
- Token-endpoint errors raise :class:`TokenExchangeError`.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from aqp.auth.oidc_client import (
    DiscoveryUnavailableError,
    OidcHttpClient,
    TokenExchangeError,
    reset_discovery_cache,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_discovery_cache()
    yield
    reset_discovery_cache()


def _mock_response(status_code: int = 200, json_body=None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body or {}
    response.text = ""
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "boom", request=MagicMock(), response=response
        )
    return response


def test_discovery_caches_response():
    client = OidcHttpClient(discovery_url="https://idp.example.com")
    payload = {"issuer": "https://idp.example.com", "jwks_uri": "https://idp.example.com/keys"}
    with patch.object(client._client, "get", return_value=_mock_response(200, payload)) as mock_get:
        a = client.discovery()
        b = client.discovery()
    assert a == payload
    assert b == payload
    assert mock_get.call_count == 1


def test_discovery_appends_well_known_suffix_when_missing():
    client = OidcHttpClient(discovery_url="https://idp.example.com/realms/aqp")
    with patch.object(client._client, "get", return_value=_mock_response(200, {"a": 1})) as mock_get:
        client.discovery()
    called_url = mock_get.call_args.args[0]
    assert called_url == "https://idp.example.com/realms/aqp/.well-known/openid-configuration"


def test_jwks_reads_from_discovery_jwks_uri():
    client = OidcHttpClient(discovery_url="https://idp.example.com")
    discovery = {"jwks_uri": "https://idp.example.com/keys"}
    jwks = {"keys": [{"kid": "k1", "kty": "RSA"}]}
    responses = [_mock_response(200, discovery), _mock_response(200, jwks)]
    with patch.object(client._client, "get", side_effect=responses):
        out = client.jwks()
    assert out == jwks


def test_exchange_code_posts_authorization_code_grant():
    client = OidcHttpClient(discovery_url="https://idp.example.com")
    with patch.object(client._client, "get", return_value=_mock_response(200, {"token_endpoint": "https://idp.example.com/token"})), patch.object(
        client._client,
        "post",
        return_value=_mock_response(
            200,
            {"access_token": "abc", "id_token": "id", "expires_in": 3600},
        ),
    ) as mock_post:
        result = client.exchange_code(
            client_id="aqp",
            client_secret="secret",
            code="auth-code",
            redirect_uri="http://localhost/cb",
            code_verifier="verifier",
        )
    assert result["access_token"] == "abc"
    body = mock_post.call_args.kwargs["data"]
    assert body["grant_type"] == "authorization_code"
    assert body["code"] == "auth-code"
    assert body["code_verifier"] == "verifier"


def test_client_credentials_passes_audience_and_scope():
    client = OidcHttpClient(discovery_url="https://idp.example.com")
    with patch.object(client._client, "get", return_value=_mock_response(200, {"token_endpoint": "https://idp.example.com/token"})), patch.object(
        client._client,
        "post",
        return_value=_mock_response(
            200,
            {"access_token": "m2m", "expires_in": 900, "scope": "polaris:write"},
        ),
    ) as mock_post:
        result = client.client_credentials(
            client_id="aqp",
            client_secret="secret",
            audience="aqp-api",
            scope="polaris:write",
        )
    assert result["access_token"] == "m2m"
    body = mock_post.call_args.kwargs["data"]
    assert body["grant_type"] == "client_credentials"
    assert body["audience"] == "aqp-api"
    assert body["scope"] == "polaris:write"


def test_token_endpoint_error_raises_token_exchange_error():
    client = OidcHttpClient(discovery_url="https://idp.example.com")
    with patch.object(client._client, "get", return_value=_mock_response(200, {"token_endpoint": "https://idp.example.com/token"})), patch.object(
        client._client,
        "post",
        return_value=_mock_response(
            400,
            {"error": "invalid_grant", "error_description": "bad code"},
        ),
    ):
        with pytest.raises(TokenExchangeError, match="bad code"):
            client.exchange_code(
                client_id="aqp",
                client_secret="secret",
                code="bad",
                redirect_uri="http://localhost/cb",
                code_verifier="v",
            )


def test_discovery_unavailable_when_url_empty():
    client = OidcHttpClient(discovery_url="")
    with pytest.raises(DiscoveryUnavailableError):
        client.discovery()
