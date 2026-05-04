"""Apache Polaris management API client.

Implements just the subset of OAuth + management endpoints needed to
bootstrap a local AQP catalog: catalog/principal/role/grant CRUD plus a
small ``ensure_*`` helpers used by :mod:`aqp.services.iceberg_bootstrap`.

The client is intentionally sync httpx-based with structured logging so
callers can run it from FastAPI startup, Celery tasks, and tests.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from aqp.config import settings
from aqp.observability import get_tracer

logger = logging.getLogger(__name__)
_tracer = get_tracer("aqp.services.polaris_client")


class PolarisClientError(RuntimeError):
    """Raised when the Polaris management API returns an error response."""


@dataclass
class PolarisAuth:
    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    scope: str = "PRINCIPAL_ROLE:ALL"


@dataclass
class PolarisClientConfig:
    base_url: str
    realm: str
    client_id: str
    client_secret: str
    timeout_seconds: float = 10.0
    extra_headers: dict[str, str] = field(default_factory=dict)


def default_polaris_config() -> PolarisClientConfig:
    """Return a :class:`PolarisClientConfig` derived from AQP settings."""
    base = (settings.polaris_base_url or "http://localhost:8181").rstrip("/")
    realm = settings.polaris_realm or "POLARIS"
    extra: dict[str, str] = {f"{realm}-Realm": realm} if realm else {}
    extra.setdefault("Polaris-Realm", realm)
    return PolarisClientConfig(
        base_url=base,
        realm=realm,
        client_id=settings.polaris_client_id or "root",
        client_secret=settings.polaris_client_secret or "s3cr3t",
        extra_headers=extra,
    )


class PolarisClient:
    """Small typed wrapper around the Polaris OAuth + management API."""

    def __init__(
        self,
        config: PolarisClientConfig | None = None,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config or default_polaris_config()
        self._client = client or httpx.Client(timeout=self.config.timeout_seconds)
        self._auth: PolarisAuth | None = None
        self._owns_client = client is None

    def __enter__(self) -> PolarisClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # ------------------------------------------------------------------
    # OAuth
    # ------------------------------------------------------------------

    def oauth_token(self, *, force: bool = False) -> PolarisAuth:
        """Exchange client credentials for a bearer access token.

        Polaris exposes the OAuth endpoint under the catalog API path, so
        the request goes to ``{base}/api/catalog/v1/oauth/tokens`` with a
        form-encoded body and basic auth via the client id/secret pair.
        """
        if self._auth and not force:
            return self._auth
        url = f"{self.config.base_url}/api/catalog/v1/oauth/tokens"
        payload = {
            "grant_type": "client_credentials",
            "scope": "PRINCIPAL_ROLE:ALL",
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }
        with _tracer.start_as_current_span("polaris.oauth_token") as span:
            span.set_attribute("polaris.url", url)
            try:
                response = self._client.post(
                    url,
                    data=payload,
                    headers={
                        "Accept": "application/json",
                        **self.config.extra_headers,
                    },
                )
            except httpx.HTTPError as exc:
                raise PolarisClientError(f"OAuth request failed: {exc}") from exc
            if response.status_code >= 400:
                raise PolarisClientError(
                    f"OAuth token exchange failed ({response.status_code}): {response.text[:300]}"
                )
            body = response.json()
        token = str(body.get("access_token") or "")
        if not token:
            raise PolarisClientError(f"OAuth response missing access_token: {body!r}")
        self._auth = PolarisAuth(
            access_token=token,
            token_type=str(body.get("token_type") or "Bearer"),
            expires_in=body.get("expires_in"),
            scope=str(body.get("scope") or "PRINCIPAL_ROLE:ALL"),
        )
        return self._auth

    # ------------------------------------------------------------------
    # Generic request helper
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: dict[str, Any] | None = None,
        ok_statuses: tuple[int, ...] = (200, 201, 204, 409),
        retries_on_401: int = 1,
    ) -> httpx.Response:
        url = f"{self.config.base_url}{path if path.startswith('/') else '/' + path}"
        attempts = 0
        while True:
            auth = self.oauth_token()
            headers = {
                "Accept": "application/json",
                "Authorization": f"{auth.token_type} {auth.access_token}",
                **self.config.extra_headers,
            }
            if json_body is not None:
                headers["Content-Type"] = "application/json"
            with _tracer.start_as_current_span(f"polaris.{method.lower()}") as span:
                span.set_attribute("polaris.url", url)
                span.set_attribute("http.method", method)
                try:
                    response = self._client.request(
                        method,
                        url,
                        headers=headers,
                        params=params,
                        content=json.dumps(json_body) if json_body is not None else None,
                    )
                except httpx.HTTPError as exc:
                    raise PolarisClientError(f"{method} {url} failed: {exc}") from exc
                span.set_attribute("http.status_code", response.status_code)
            if response.status_code == 401 and attempts < retries_on_401:
                attempts += 1
                self._auth = None
                continue
            if response.status_code in ok_statuses or 200 <= response.status_code < 300:
                return response
            raise PolarisClientError(
                f"{method} {url} failed ({response.status_code}): {response.text[:500]}"
            )

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any]:
        if not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError:
            return {"text": response.text}
        return payload if isinstance(payload, dict) else {"data": payload}

    # ------------------------------------------------------------------
    # Catalogs
    # ------------------------------------------------------------------

    def list_catalogs(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/api/management/v1/catalogs")
        body = self._safe_json(response)
        catalogs = body.get("catalogs") or body.get("data") or []
        return [c for c in catalogs if isinstance(c, dict)]

    def get_catalog(self, name: str) -> dict[str, Any] | None:
        try:
            response = self._request("GET", f"/api/management/v1/catalogs/{name}")
        except PolarisClientError as exc:
            if "404" in str(exc):
                return None
            raise
        if response.status_code == 404:
            return None
        return self._safe_json(response)

    def create_catalog(
        self,
        name: str,
        *,
        default_base_location: str,
        storage_type: str = "FILE",
        s3: dict[str, Any] | None = None,
        properties: dict[str, str] | None = None,
        catalog_type: str = "INTERNAL",
    ) -> dict[str, Any]:
        """Create a Polaris catalog idempotently.

        ``storage_type`` should be one of ``FILE``, ``S3``, ``GCS``,
        ``AZURE``. For S3, pass an ``s3`` dict with ``endpoint``,
        ``region``, ``access_key``, ``secret_key`` and optional
        ``role_arn`` / ``allowed_locations``.
        """
        existing = self.get_catalog(name)
        if existing:
            return existing
        storage_config: dict[str, Any] = {
            "storageType": storage_type.upper(),
            "allowedLocations": [default_base_location],
        }
        s3 = s3 or {}
        if storage_type.upper() == "S3":
            storage_config.update(
                {
                    "endpoint": s3.get("endpoint", ""),
                    "region": s3.get("region", ""),
                    "pathStyleAccess": bool(s3.get("path_style_access", True)),
                }
            )
            if s3.get("role_arn"):
                storage_config["roleArn"] = s3["role_arn"]
            if s3.get("external_id"):
                storage_config["externalId"] = s3["external_id"]
            for extra in s3.get("allowed_locations") or []:
                if extra and extra not in storage_config["allowedLocations"]:
                    storage_config["allowedLocations"].append(extra)
        body = {
            "catalog": {
                "name": name,
                "type": catalog_type,
                "properties": dict(properties or {"default-base-location": default_base_location}),
                "storageConfigInfo": storage_config,
            }
        }
        response = self._request("POST", "/api/management/v1/catalogs", json_body=body)
        return self._safe_json(response) or {"name": name, "created": True}

    # ------------------------------------------------------------------
    # Principals + roles + grants
    # ------------------------------------------------------------------

    def get_principal(self, name: str) -> dict[str, Any] | None:
        response = self._request(
            "GET",
            f"/api/management/v1/principals/{name}",
            ok_statuses=(200, 404),
        )
        if response.status_code == 404:
            return None
        return self._safe_json(response)

    def create_principal(self, name: str, *, properties: dict[str, str] | None = None) -> dict[str, Any]:
        existing = self.get_principal(name)
        if existing and existing.get("credentials") is None:
            return existing
        body = {
            "principal": {
                "name": name,
                "properties": dict(properties or {}),
            },
            "credentialRotationRequired": False,
        }
        response = self._request("POST", "/api/management/v1/principals", json_body=body)
        return self._safe_json(response) or {"name": name, "created": True}

    def get_principal_role(self, name: str) -> dict[str, Any] | None:
        response = self._request(
            "GET",
            f"/api/management/v1/principal-roles/{name}",
            ok_statuses=(200, 404),
        )
        if response.status_code == 404:
            return None
        return self._safe_json(response)

    def create_principal_role(self, name: str) -> dict[str, Any]:
        existing = self.get_principal_role(name)
        if existing:
            return existing
        body = {"principalRole": {"name": name}}
        response = self._request("POST", "/api/management/v1/principal-roles", json_body=body)
        return self._safe_json(response) or {"name": name, "created": True}

    def assign_principal_role(self, *, principal: str, principal_role: str) -> None:
        body = {"principalRole": {"name": principal_role}}
        self._request(
            "PUT",
            f"/api/management/v1/principals/{principal}/principal-roles",
            json_body=body,
        )

    def get_catalog_role(self, *, catalog: str, role: str) -> dict[str, Any] | None:
        response = self._request(
            "GET",
            f"/api/management/v1/catalogs/{catalog}/catalog-roles/{role}",
            ok_statuses=(200, 404),
        )
        if response.status_code == 404:
            return None
        return self._safe_json(response)

    def create_catalog_role(self, *, catalog: str, role: str) -> dict[str, Any]:
        existing = self.get_catalog_role(catalog=catalog, role=role)
        if existing:
            return existing
        body = {"catalogRole": {"name": role}}
        response = self._request(
            "POST",
            f"/api/management/v1/catalogs/{catalog}/catalog-roles",
            json_body=body,
        )
        return self._safe_json(response) or {"name": role, "created": True}

    def assign_catalog_role(
        self,
        *,
        catalog: str,
        principal_role: str,
        catalog_role: str,
    ) -> None:
        body = {"catalogRole": {"name": catalog_role}}
        self._request(
            "PUT",
            f"/api/management/v1/principal-roles/{principal_role}/catalog-roles/{catalog}",
            json_body=body,
        )

    def grant_catalog_privilege(
        self,
        *,
        catalog: str,
        catalog_role: str,
        privilege: str = "CATALOG_MANAGE_CONTENT",
    ) -> None:
        body = {"grant": {"type": "catalog", "privilege": privilege}}
        self._request(
            "PUT",
            f"/api/management/v1/catalogs/{catalog}/catalog-roles/{catalog_role}/grants",
            json_body=body,
        )


__all__ = [
    "PolarisAuth",
    "PolarisClient",
    "PolarisClientConfig",
    "PolarisClientError",
    "default_polaris_config",
]
