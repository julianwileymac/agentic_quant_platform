"""Small Superset REST client used by the visualization layer."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from aqp.config import settings
from aqp.observability import get_tracer

logger = logging.getLogger(__name__)
_TRACER = get_tracer("aqp.visualization.superset_client")


@dataclass(frozen=True)
class SupersetAuth:
    access_token: str
    refresh_token: str | None = None
    csrf_token: str | None = None


class SupersetClient:
    """Authenticated wrapper for the subset of Superset APIs AQP provisions."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        provider: str | None = None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or settings.superset_base_url).rstrip("/")
        self.username = username or settings.superset_username
        self.password = password or settings.superset_password
        self.provider = provider or settings.superset_provider
        self._client = client or httpx.Client(timeout=timeout)
        self._auth: SupersetAuth | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SupersetClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def auth(self) -> SupersetAuth:
        if self._auth is None:
            self._auth = self.login()
        return self._auth

    def login(self) -> SupersetAuth:
        payload = {
            "username": self.username,
            "password": self.password,
            "provider": self.provider,
            "refresh": True,
        }
        data = self._request("POST", "/api/v1/security/login", json=payload, auth=False)
        result = data.get("result") if isinstance(data.get("result"), dict) else data
        token = str(result.get("access_token") or "")
        if not token:
            raise RuntimeError("Superset login did not return an access token")
        return SupersetAuth(
            access_token=token,
            refresh_token=result.get("refresh_token"),
        )

    def csrf_token(self) -> str:
        auth = self.auth
        if auth.csrf_token:
            return auth.csrf_token
        data = self._request("GET", "/api/v1/security/csrf_token/", auth=True)
        token = str(data.get("result") or data.get("csrf_token") or "")
        if not token:
            raise RuntimeError("Superset CSRF endpoint did not return a token")
        self._auth = SupersetAuth(
            access_token=auth.access_token,
            refresh_token=auth.refresh_token,
            csrf_token=token,
        )
        return token

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health", auth=False)

    def create_guest_token(
        self,
        *,
        resources: list[dict[str, str]],
        rls: list[dict[str, str]] | None = None,
        user: dict[str, str] | None = None,
    ) -> str:
        payload = {
            "resources": resources,
            "rls": rls or [],
            "user": user
            or {
                "username": settings.superset_guest_username,
                "first_name": settings.superset_guest_first_name,
                "last_name": settings.superset_guest_last_name,
            },
        }
        data = self._request(
            "POST",
            "/api/v1/security/guest_token/",
            json=payload,
            auth=True,
            csrf=True,
        )
        token = str(data.get("token") or data.get("result", {}).get("token") or "")
        if not token:
            raise RuntimeError("Superset guest-token endpoint did not return a token")
        return token

    def create_database(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/v1/database/", json=payload, auth=True, csrf=True)

    def update_database(self, database_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/api/v1/database/{database_id}",
            json=payload,
            auth=True,
            csrf=True,
        )

    def list_databases(self) -> list[dict[str, Any]]:
        return self._list("/api/v1/database/")

    def create_dataset(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/v1/dataset/", json=payload, auth=True, csrf=True)

    def update_dataset(self, dataset_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/api/v1/dataset/{dataset_id}",
            json=payload,
            auth=True,
            csrf=True,
        )

    def list_datasets(self) -> list[dict[str, Any]]:
        return self._list("/api/v1/dataset/")

    def create_chart(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/v1/chart/", json=payload, auth=True, csrf=True)

    def update_chart(self, chart_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/api/v1/chart/{chart_id}", json=payload, auth=True, csrf=True)

    def list_charts(self) -> list[dict[str, Any]]:
        return self._list("/api/v1/chart/")

    def create_dashboard(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/v1/dashboard/", json=payload, auth=True, csrf=True)

    def update_dashboard(self, dashboard_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/api/v1/dashboard/{dashboard_id}",
            json=payload,
            auth=True,
            csrf=True,
        )

    def list_dashboards(self) -> list[dict[str, Any]]:
        return self._list("/api/v1/dashboard/")

    def _list(self, path: str) -> list[dict[str, Any]]:
        data = self._request("GET", path, params={"page_size": 1000}, auth=True)
        result = data.get("result", data)
        rows = result.get("result") if isinstance(result, dict) else result
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool,
        csrf: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        headers = dict(kwargs.pop("headers", {}) or {})
        with _TRACER.start_as_current_span(f"superset.client.{method.lower()}") as span:
            span.set_attribute("http.method", method)
            span.set_attribute("http.url", url)
            span.set_attribute("superset.path", path)
            span.set_attribute("superset.auth", auth)
            span.set_attribute("superset.csrf", csrf)
            if auth:
                headers["Authorization"] = f"Bearer {self.auth.access_token}"
            if csrf:
                headers["X-CSRFToken"] = self.csrf_token()
                headers["Referer"] = self.base_url
            response = self._client.request(method, url, headers=headers, **kwargs)
            span.set_attribute("http.status_code", response.status_code)
            if response.status_code >= 400:
                # Capture the response body in the log/exception so callers
                # can debug 4xx validation failures without re-running the
                # request manually with a debugger.
                try:
                    detail = response.json()
                except ValueError:
                    detail = response.text
                logger.warning(
                    "Superset %s %s failed (%s): %s",
                    method,
                    path,
                    response.status_code,
                    detail,
                )
                span.set_attribute("superset.error", str(detail)[:512])
            response.raise_for_status()
            if not response.content:
                return {}
            try:
                data = response.json()
            except ValueError:
                return {"text": response.text}
            return data if isinstance(data, dict) else {"result": data}
