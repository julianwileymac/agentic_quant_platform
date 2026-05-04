from __future__ import annotations

import httpx
import pytest


@pytest.fixture
def polaris_client():
    from aqp.services.polaris_client import PolarisClient, PolarisClientConfig

    config = PolarisClientConfig(
        base_url="http://polaris:8181",
        realm="POLARIS",
        client_id="root",
        client_secret="s3cr3t",
        extra_headers={"Polaris-Realm": "POLARIS"},
    )

    def _factory(handler):
        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)
        return PolarisClient(config, client=client)

    return _factory


def test_oauth_token_uses_form_body(polaris_client):
    captured: dict[str, object] = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 600},
        )

    with polaris_client(handler) as client:
        auth = client.oauth_token()

    assert auth.access_token == "token-123"
    header_keys = {key.lower() for key in captured["headers"]}
    assert "polaris-realm" in header_keys
    assert "grant_type=client_credentials" in captured["body"]
    assert "client_id=root" in captured["body"]


def test_create_catalog_skips_existing(polaris_client):
    calls: list[str] = []

    def handler(request):
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path.endswith("/oauth/tokens"):
            return httpx.Response(200, json={"access_token": "token"})
        if request.method == "GET" and request.url.path.endswith("/catalogs/quickstart_catalog"):
            return httpx.Response(200, json={"name": "quickstart_catalog", "type": "INTERNAL"})
        return httpx.Response(404, json={"error": "not found"})

    with polaris_client(handler) as client:
        result = client.create_catalog(
            "quickstart_catalog",
            default_base_location="file:///tmp",
        )

    assert result["name"] == "quickstart_catalog"
    assert any("/catalogs/quickstart_catalog" in c for c in calls)
    assert not any(c == "POST /api/management/v1/catalogs" for c in calls)


def test_create_catalog_posts_when_missing(polaris_client):
    posted: dict[str, object] = {}

    def handler(request):
        if request.url.path.endswith("/oauth/tokens"):
            return httpx.Response(200, json={"access_token": "token"})
        if request.method == "GET" and request.url.path.endswith("/catalogs/quickstart_catalog"):
            return httpx.Response(404)
        if request.method == "POST" and request.url.path == "/api/management/v1/catalogs":
            posted["body"] = request.content.decode()
            return httpx.Response(201, json={"name": "quickstart_catalog", "created": True})
        return httpx.Response(500)

    with polaris_client(handler) as client:
        result = client.create_catalog(
            "quickstart_catalog",
            default_base_location="s3://bucket/x",
            storage_type="S3",
            s3={"endpoint": "http://minio:9000", "region": "us-east-1"},
        )

    assert result["created"] is True
    assert "storageConfigInfo" in posted["body"]


def test_create_principal_returns_credentials(polaris_client):
    def handler(request):
        if request.url.path.endswith("/oauth/tokens"):
            return httpx.Response(200, json={"access_token": "token"})
        if request.method == "GET" and request.url.path.endswith("/principals/aqp_runtime"):
            return httpx.Response(404)
        if request.method == "POST" and request.url.path == "/api/management/v1/principals":
            return httpx.Response(
                201,
                json={
                    "principal": {"name": "aqp_runtime"},
                    "credentials": {"clientId": "abc", "clientSecret": "def"},
                },
            )
        return httpx.Response(500)

    with polaris_client(handler) as client:
        result = client.create_principal("aqp_runtime")

    assert result["credentials"]["clientId"] == "abc"
