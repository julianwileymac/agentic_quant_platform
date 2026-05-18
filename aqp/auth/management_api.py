"""Thin Auth0 Management API v2 client for `/me/*` mutations."""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx
from httpx_retries import Retry, RetryTransport

from aqp.config import settings
from aqp.credentials import CredentialKey, get_resolver

logger = logging.getLogger(__name__)

_CREDENTIAL_KEY = "auth0_mgmt_api.client_secret"
_REQUEST_TIMEOUT_SECONDS = 10.0
_TOKEN_SKEW_SECONDS = 60
_SCOPE_RE = re.compile(r"scope(?:s)?[=: ]+([a-zA-Z0-9:._ -]+)", re.IGNORECASE)
_WWW_AUTH_SCOPE_RE = re.compile(r'scope="([^"]+)"', re.IGNORECASE)


class Auth0ManagementError(Exception):
    """Raised for Auth0 Management API transport/status failures."""


@dataclass(frozen=True)
class Auth0Session:
    id: str
    user_id: str
    created_at: str
    updated_at: str
    last_activity: str | None
    ip: str | None
    user_agent: str | None
    device: str | None
    location: str | None


@dataclass(frozen=True)
class Auth0Factor:
    id: str
    type: str
    name: str | None
    enrolled_at: str
    confirmed: bool
    phone_number: str | None


@dataclass(frozen=True)
class Auth0PasswordTicket:
    ticket: str
    expires_at: str


@dataclass(frozen=True)
class Auth0MfaEnrollmentTicket:
    ticket_id: str
    ticket_url: str
    qr_code_url: str | None
    secret: str | None
    recovery_codes: list[str]
    expires_at: str


@dataclass(frozen=True)
class Auth0LogEvent:
    log_id: str
    date: str
    type: str
    description: str | None
    ip: str | None
    user_agent: str | None
    connection: str | None


class Auth0ManagementClient:
    """Synchronous Auth0 Management API wrapper.

    The constructor is side-effect free: no network request is made until a
    public API method is invoked.
    """

    def __init__(self) -> None:
        self._audience = str(settings.auth0_mgmt_api_audience or "").strip()
        self._client_id = str(settings.auth0_mgmt_api_client_id or "").strip()
        self._http = self._build_http_client()
        self._config_lock = threading.RLock()
        self._token_lock = threading.RLock()
        self._base_url: str | None = None
        self._api_prefix: str | None = None
        self._access_token: str | None = None
        self._access_token_expires_at: float = 0.0

    # ------------------------------------------------------------------ Users
    def get_user(self, user_id: str) -> dict[str, Any]:
        path = f"/users/{_encode_segment(user_id)}"
        return self._request_json("GET", path, not_found=user_id)

    def update_user(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        path = f"/users/{_encode_segment(user_id)}"
        return self._request_json("PATCH", path, json_body=patch, not_found=user_id)

    def delete_user(self, user_id: str) -> None:
        path = f"/users/{_encode_segment(user_id)}"
        self._request("DELETE", path, not_found=user_id)

    # --------------------------------------------------------------- Sessions
    def list_user_sessions(self, user_id: str) -> list[Auth0Session]:
        path = f"/users/{_encode_segment(user_id)}/sessions"
        payload = self._request_json("GET", path, not_found=user_id)
        if not isinstance(payload, list):
            return []
        sessions: list[Auth0Session] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            session_id = _first_text(row, "id", "session_id")
            if not session_id:
                continue
            sessions.append(
                Auth0Session(
                    id=session_id,
                    user_id=_first_text(row, "user_id") or user_id,
                    created_at=_first_text(row, "created_at", "createdAt"),
                    updated_at=_first_text(row, "updated_at", "updatedAt"),
                    last_activity=_nullable_text(row, "last_activity", "lastActivity"),
                    ip=_nullable_text(row, "ip"),
                    user_agent=_nullable_text(row, "user_agent", "userAgent"),
                    device=_nullable_text(row, "device"),
                    location=_location_text(row.get("location")),
                )
            )
        return sessions

    def revoke_session(self, session_id: str) -> None:
        path = f"/sessions/{_encode_segment(session_id)}"
        self._request("DELETE", path, not_found=session_id)

    def revoke_all_sessions_for_user(self, user_id: str) -> int:
        active_sessions = self.list_user_sessions(user_id)
        path = f"/users/{_encode_segment(user_id)}/sessions"
        self._request("DELETE", path, not_found=user_id)
        return len(active_sessions)

    # ---------------------------------------------- MFA / authentication methods
    def list_authentication_methods(self, user_id: str) -> list[Auth0Factor]:
        path = f"/users/{_encode_segment(user_id)}/authentication-methods"
        payload = self._request_json("GET", path, not_found=user_id)
        if not isinstance(payload, list):
            return []
        factors: list[Auth0Factor] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            factor_id = _first_text(row, "id", "authenticator_id")
            if not factor_id:
                continue
            factor_type = _first_text(row, "type", "authenticator_type")
            phone = _nullable_text(row, "phone_number", "phoneNumber")
            factors.append(
                Auth0Factor(
                    id=factor_id,
                    type=factor_type,
                    name=_nullable_text(row, "name", "device_name"),
                    enrolled_at=_first_text(row, "enrolled_at", "created_at", "createdAt"),
                    confirmed=bool(row.get("confirmed", True)),
                    phone_number=_mask_phone_suffix(phone) if factor_type == "sms" else None,
                )
            )
        return factors

    def delete_authentication_method(self, user_id: str, method_id: str) -> None:
        path = (
            f"/users/{_encode_segment(user_id)}/authentication-methods/"
            f"{_encode_segment(method_id)}"
        )
        self._request("DELETE", path, not_found=method_id)

    def create_mfa_enrollment_ticket(
        self,
        user_id: str,
        factor: str,
        *,
        return_url: str | None = None,
    ) -> Auth0MfaEnrollmentTicket:
        body: dict[str, Any] = {"user_id": user_id, "send_mail": False, "factor": factor}
        if return_url:
            body["return_url"] = return_url
        payload = self._request_json("POST", "/guardian/enrollments/ticket", json_body=body)
        if not isinstance(payload, dict):
            raise Auth0ManagementError("upstream 5xx: malformed mfa enrollment ticket payload")
        return Auth0MfaEnrollmentTicket(
            ticket_id=_first_text(payload, "ticket_id", "id", "ticket"),
            ticket_url=_first_text(payload, "ticket_url", "ticket"),
            qr_code_url=_nullable_text(payload, "qr_code_url", "qrCodeUrl"),
            secret=_nullable_text(payload, "secret"),
            recovery_codes=_string_list(
                payload.get("recovery_codes") or payload.get("recoveryCodes")
            ),
            expires_at=_resolve_expires_at(payload),
        )

    # --------------------------------------------------------------- Password
    def create_password_change_ticket(
        self,
        user_id: str,
        *,
        return_url: str,
    ) -> Auth0PasswordTicket:
        body = {
            "user_id": user_id,
            "result_url": return_url,
            "mark_email_as_verified": False,
        }
        payload = self._request_json("POST", "/tickets/password-change", json_body=body)
        if not isinstance(payload, dict):
            raise Auth0ManagementError("upstream 5xx: malformed password ticket payload")
        return Auth0PasswordTicket(
            ticket=_first_text(payload, "ticket", "ticket_url"),
            expires_at=_resolve_expires_at(payload),
        )

    # ------------------------------------------------------- Connected accounts
    def link_account(
        self,
        primary_user_id: str,
        *,
        secondary_jwt: str,
    ) -> list[dict[str, Any]]:
        path = f"/users/{_encode_segment(primary_user_id)}/identities"
        payload = self._request_json("POST", path, json_body={"link_with": secondary_jwt})
        return _coerce_dict_list(payload)

    def unlink_account(
        self,
        primary_user_id: str,
        *,
        provider: str,
        secondary_user_id: str,
    ) -> list[dict[str, Any]]:
        path = (
            f"/users/{_encode_segment(primary_user_id)}/identities/{_encode_segment(provider)}"
            f"/{_encode_segment(secondary_user_id)}"
        )
        payload = self._request_json("DELETE", path, not_found=secondary_user_id)
        return _coerce_dict_list(payload)

    # ----------------------------------------------------------------- Logs
    def list_user_logs(
        self,
        user_id: str,
        *,
        per_page: int = 50,
        page: int = 0,
    ) -> list[Auth0LogEvent]:
        path = f"/users/{_encode_segment(user_id)}/logs"
        payload = self._request_json(
            "GET",
            path,
            params={"per_page": int(per_page), "page": int(page)},
            not_found=user_id,
        )
        if not isinstance(payload, list):
            return []
        events: list[Auth0LogEvent] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            events.append(
                Auth0LogEvent(
                    log_id=_first_text(row, "log_id", "_id", "id"),
                    date=_first_text(row, "date"),
                    type=_first_text(row, "type"),
                    description=_nullable_text(row, "description"),
                    ip=_nullable_text(row, "ip"),
                    user_agent=_nullable_text(row, "user_agent", "userAgent"),
                    connection=_nullable_text(row, "connection"),
                )
            )
        return events

    # ------------------------------------------------------------ Connections
    def list_connections(self, *, strategy: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] | None = None
        if strategy:
            params = {"strategy": strategy}
        payload = self._request_json("GET", "/connections", params=params)
        return _coerce_dict_list(payload)

    # ---------------------------------------------------------------- Diagnostics
    def describe(self) -> dict[str, Any]:
        audience = str(self._audience or settings.auth0_mgmt_api_audience or "").strip()
        secret = self._resolve_client_secret()
        ttl_s = 0
        if self._access_token:
            ttl_s = max(0, int(self._access_token_expires_at - time.time()))
        return {
            "audience": audience,
            "has_secret": bool(secret),
            "token_ttl_s": ttl_s,
        }

    # ---------------------------------------------------------------- Internals
    def _build_http_client(self) -> httpx.Client:
        retry = Retry(
            total=3,
            allowed_methods={"GET", "POST", "PATCH", "DELETE"},
            status_forcelist={429},
            respect_retry_after_header=True,
            backoff_factor=0.0,
        )
        transport = RetryTransport(retry=retry)
        return httpx.Client(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT_SECONDS),
            transport=transport,
            headers={"Accept": "application/json"},
        )

    def _resolve_api_urls(self) -> tuple[str, str]:
        if self._base_url and self._api_prefix:
            return self._base_url, self._api_prefix
        with self._config_lock:
            if self._base_url and self._api_prefix:
                return self._base_url, self._api_prefix
            audience = str(self._audience or settings.auth0_mgmt_api_audience or "").strip()
            if not audience:
                raise Auth0ManagementError("auth0 management audience is empty")
            normalized = audience.rstrip("/")
            suffix = "/api/v2"
            if not normalized.endswith(suffix):
                raise Auth0ManagementError(
                    "auth0 management audience must end with /api/v2/"
                )
            base_url = normalized[: -len(suffix)]
            if not base_url:
                raise Auth0ManagementError("auth0 management audience is invalid")
            self._base_url = base_url
            self._api_prefix = f"{base_url}/api/v2"
            return self._base_url, self._api_prefix

    def _resolve_client_secret(self) -> str:
        service, purpose = _CREDENTIAL_KEY.split(".", 1)
        credential = get_resolver().resolve(
            CredentialKey(service=service, purpose=purpose),
            default={"value": str(settings.auth0_mgmt_api_client_secret or "")},
        )
        value = (
            credential.get("client_secret")
            or credential.get("secret")
            or credential.get("value")
            or ""
        )
        return str(value).strip()

    def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._access_token_expires_at:
            return self._access_token
        with self._token_lock:
            now = time.time()
            if self._access_token and now < self._access_token_expires_at:
                return self._access_token
            token, expires_at = self._mint_access_token()
            self._access_token = token
            self._access_token_expires_at = expires_at
            return token

    def _mint_access_token(self) -> tuple[str, float]:
        base_url, _ = self._resolve_api_urls()
        client_id = str(self._client_id or settings.auth0_mgmt_api_client_id or "").strip()
        client_secret = self._resolve_client_secret()
        if not client_id or not client_secret:
            raise Auth0ManagementError("invalid credentials")
        body = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "audience": str(self._audience or settings.auth0_mgmt_api_audience or "").strip(),
        }
        endpoint = f"{base_url}/oauth/token"
        try:
            response = self._http.post(endpoint, json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._map_http_error(exc) from exc
        except httpx.HTTPError as exc:
            raise Auth0ManagementError(f"network failure: {exc}") from exc
        payload = _json_or_empty_dict(response)
        access_token = _first_text(payload, "access_token")
        expires_in = int(payload.get("expires_in") or 0)
        if not access_token or expires_in <= 0:
            raise Auth0ManagementError("upstream 5xx: malformed oauth/token response")
        cache_seconds = max(1, expires_in - _TOKEN_SKEW_SECONDS)
        return access_token, time.time() + cache_seconds

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        not_found: str | None = None,
    ) -> httpx.Response:
        _, api_prefix = self._resolve_api_urls()
        url = f"{api_prefix}{path}"
        headers = {"Authorization": f"Bearer {self._get_access_token()}"}
        try:
            response = self._http.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=headers,
            )
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            raise self._map_http_error(exc, not_found=not_found) from exc
        except httpx.HTTPError as exc:
            raise Auth0ManagementError(f"network failure: {exc}") from exc

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        not_found: str | None = None,
    ) -> Any:
        response = self._request(
            method,
            path,
            params=params,
            json_body=json_body,
            not_found=not_found,
        )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {}

    def _map_http_error(
        self,
        exc: httpx.HTTPStatusError,
        *,
        not_found: str | None = None,
    ) -> Auth0ManagementError:
        response = exc.response
        status_code = int(response.status_code)
        detail = _response_detail(response)
        if status_code == 401:
            return Auth0ManagementError("invalid credentials")
        if status_code == 403:
            scope = _required_scope(response) or "<unknown>"
            return Auth0ManagementError(f"scope {scope} required: {detail}")
        if status_code == 404:
            return Auth0ManagementError(f"not found: {not_found or detail}")
        if status_code == 429:
            return Auth0ManagementError("rate limit exceeded after retries")
        if 500 <= status_code <= 599:
            return Auth0ManagementError(f"upstream 5xx: {detail}")
        return Auth0ManagementError(f"upstream {status_code}: {detail}")


_CLIENT: Auth0ManagementClient | None = None
_CLIENT_LOCK = threading.RLock()


def get_management_client() -> Auth0ManagementClient:
    """Return the process-wide Auth0 Management API client."""
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                _CLIENT = Auth0ManagementClient()
    return _CLIENT


def reset_management_client() -> None:
    """Drop the cached client. Used by tests + the M3 wiring."""
    global _CLIENT
    with _CLIENT_LOCK:
        _CLIENT = None


def _encode_segment(value: str) -> str:
    return quote(str(value), safe="")


def _first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _nullable_text(payload: dict[str, Any], *keys: str) -> str | None:
    value = _first_text(payload, *keys)
    return value or None


def _json_or_empty_dict(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _response_detail(response: httpx.Response) -> str:
    payload = _json_or_empty_dict(response)
    for key in ("error_description", "message", "description", "error"):
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    text = (response.text or "").strip()
    if text:
        return text[:500]
    return f"HTTP {response.status_code}"


def _required_scope(response: httpx.Response) -> str | None:
    payload = _json_or_empty_dict(response)
    required_scope = payload.get("required_scope")
    if isinstance(required_scope, str) and required_scope.strip():
        return required_scope.strip()
    required_scopes = payload.get("required_scopes")
    if isinstance(required_scopes, list):
        values = [str(item).strip() for item in required_scopes if str(item).strip()]
        if values:
            return " ".join(values)
    www_auth = response.headers.get("www-authenticate", "")
    header_match = _WWW_AUTH_SCOPE_RE.search(www_auth)
    if header_match:
        return header_match.group(1).strip()
    detail = _response_detail(response)
    detail_match = _SCOPE_RE.search(detail)
    if detail_match:
        return detail_match.group(1).strip()
    return None


def _coerce_dict_list(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    out: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            out.append(item)
    return out


def _resolve_expires_at(payload: dict[str, Any]) -> str:
    explicit = _first_text(payload, "expires_at", "expiresAt")
    if explicit:
        return explicit
    expires_in = payload.get("expires_in")
    try:
        ttl = int(expires_in)
    except (TypeError, ValueError):
        ttl = 0
    if ttl > 0:
        return _iso_in(ttl)
    return ""


def _iso_in(seconds: int) -> str:
    dt = datetime.now(tz=UTC) + timedelta(seconds=max(0, int(seconds)))
    return dt.isoformat().replace("+00:00", "Z")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _mask_phone_suffix(phone_number: str | None) -> str | None:
    if not phone_number:
        return None
    digits = "".join(ch for ch in phone_number if ch.isdigit())
    suffix = (digits[-4:] if digits else phone_number[-4:]).strip()
    if not suffix:
        return None
    return f"***{suffix}"


def _location_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("name", "label", "display"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
        city = value.get("city")
        country = value.get("country")
        if isinstance(city, str) and isinstance(country, str):
            label = f"{city.strip()}, {country.strip()}".strip(", ")
            return label or None
    return None


__all__ = [
    "Auth0Factor",
    "Auth0LogEvent",
    "Auth0ManagementClient",
    "Auth0ManagementError",
    "Auth0MfaEnrollmentTicket",
    "Auth0PasswordTicket",
    "Auth0Session",
    "get_management_client",
    "reset_management_client",
]
