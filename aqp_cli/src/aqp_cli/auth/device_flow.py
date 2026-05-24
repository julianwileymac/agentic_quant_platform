"""OAuth 2.0 Device Authorization Grant (RFC 8628) for the AQP CLI.

The Device Authorization Grant is the OAuth flow designed for
input-constrained terminals: the CLI asks the IdP for a short
``user_code`` plus a ``verification_uri``, prints them to the
operator, then polls the token endpoint until the operator has
opened the URI in a *separate* browser (on the same machine, on a
phone, or on a workstation across the office) and approved.

RFC 8628 §3.5 specifies the polling contract precisely:

> Before each new request, the client MUST wait at least the number
> of seconds specified by the 'interval' parameter of the device
> authorization response (see Section 3.2), or 5 seconds if none
> was provided, and respect any increase in the polling interval
> required by the "slow_down" error.

And the error codes (§3.5):

> authorization_pending — The authorization request is still
>   pending as the end user hasn't yet completed the user-interaction
>   steps (Section 3.3). The client SHOULD repeat the access token
>   request to the token endpoint (a process known as polling).
>
> slow_down — A variant of "authorization_pending", the authorization
>   request is still pending and polling should continue, but the
>   interval MUST be increased by 5 seconds for this and all
>   subsequent requests.
>
> access_denied — The authorization request was denied.
>
> expired_token — The "device_code" has expired, and the device
>   authorization session has concluded. The client MAY commence a
>   new device authorization request but SHOULD wait for user
>   interaction before restarting to avoid unnecessary polling.

This module implements those rules verbatim. It is intentionally
dependency-light (just ``httpx``) so the CLI's core surface stays
fast to install.

Usage::

    from aqp_cli.auth.device_flow import DeviceFlowClient

    client = DeviceFlowClient(
        domain="aqp-prod.us.auth0.com",
        client_id="<aqp-cli native app client_id>",
        audience="https://api.aqp.fund/",
    )
    tokens = client.login(scope="openid profile email offline_access")
    # tokens.access_token / tokens.refresh_token / tokens.id_token

The Auth0-specific knobs (custom domain, organization param) are
forwarded transparently — any RFC 8628-compliant IdP works because
the wire format is standardised. See ``aqp_docs/auth0-setup.md``
for the Auth0 Native Application configuration that pairs with
this client.
"""
from __future__ import annotations

import logging
import time
import webbrowser
from dataclasses import dataclass
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

GRANT_TYPE_DEVICE_CODE: str = "urn:ietf:params:oauth:grant-type:device_code"


@dataclass(frozen=True)
class DeviceAuthorizationResponse:
    """Reply to the ``/oauth/device/code`` request (RFC 8628 §3.2)."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None
    expires_in: int
    interval: int


@dataclass(frozen=True)
class DeviceFlowTokens:
    """Tokens returned by a successful Device Authorization Grant."""

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None
    id_token: str | None
    scope: str | None
    raw: dict[str, Any]

    @property
    def expires_at(self) -> float:
        return time.time() + self.expires_in


class DeviceFlowError(RuntimeError):
    """Raised when the Device Authorization flow cannot complete.

    Carries the OAuth ``error`` code as the first positional arg so
    callers can branch on ``invalid_request`` / ``access_denied`` /
    ``expired_token`` / ``server_error`` without parsing the message.
    """

    def __init__(self, code: str, description: str | None = None) -> None:
        super().__init__(description or code)
        self.code = code


class DeviceFlowCancelled(DeviceFlowError):
    """User cancelled the device flow (Ctrl-C between polls)."""

    def __init__(self) -> None:
        super().__init__("cancelled", "Device flow cancelled by the operator")


class DeviceFlowClient:
    """Drive an RFC 8628 Device Authorization Grant against an OAuth IdP.

    The client is intentionally synchronous because the CLI is
    synchronous; the polling loop is a tight ``time.sleep`` + httpx
    request, so async would just add complexity without latency wins.

    Construction is dependency-light so unit tests can swap the http
    client via constructor kwarg and tick the clock via the
    ``sleep_fn`` hook.
    """

    def __init__(
        self,
        *,
        domain: str,
        client_id: str,
        audience: str | None = None,
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 10.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        announce_fn: Callable[[str], None] | None = None,
        open_browser_fn: Callable[[str], bool] | None = None,
    ) -> None:
        self.domain = domain.strip("/")
        self.client_id = client_id
        self.audience = audience
        self._http = http_client
        self._owns_http = http_client is None
        self._timeout = timeout_seconds
        self._sleep = sleep_fn
        self._announce = announce_fn or (lambda msg: print(msg, flush=True))
        self._open_browser = open_browser_fn or _default_open_browser

    # -- public ----------------------------------------------------------

    def request_device_code(
        self,
        *,
        scope: str,
        organization: str | None = None,
        resource: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> DeviceAuthorizationResponse:
        """Step 1 — ask the IdP for a fresh ``device_code``.

        ``organization`` is the Auth0 Organizations parameter
        (institutional B2B routing). ``resource`` is the RFC 8707
        Resource Indicator (forwarded so the minted token's ``aud``
        / ``resource`` claims match the canonical MCP server URI).
        """
        body: dict[str, str] = {
            "client_id": self.client_id,
            "scope": scope,
        }
        if self.audience:
            body["audience"] = self.audience
        if organization:
            body["organization"] = organization
        if resource:
            body["resource"] = resource
        if extra_params:
            body.update(extra_params)

        endpoint = f"https://{self.domain}/oauth/device/code"
        response = self._client().post(
            endpoint,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        if response.status_code != 200:
            raise self._error_from_response(response, default_code="device_code_request_failed")
        try:
            payload = response.json()
        except ValueError as exc:
            raise DeviceFlowError(
                "invalid_response",
                "device_code endpoint returned non-JSON",
            ) from exc

        device_code = payload.get("device_code")
        user_code = payload.get("user_code")
        verification_uri = payload.get("verification_uri") or payload.get("verification_url")
        if not (isinstance(device_code, str) and isinstance(user_code, str)
                and isinstance(verification_uri, str)):
            raise DeviceFlowError(
                "invalid_response",
                "device_code response missing required fields",
            )

        return DeviceAuthorizationResponse(
            device_code=device_code,
            user_code=user_code,
            verification_uri=verification_uri,
            verification_uri_complete=payload.get("verification_uri_complete"),
            expires_in=int(payload.get("expires_in", 900)),
            interval=max(1, int(payload.get("interval", 5))),
        )

    def poll_for_tokens(
        self,
        device: DeviceAuthorizationResponse,
    ) -> DeviceFlowTokens:
        """Step 2 — poll the token endpoint until the operator approves.

        Honours RFC 8628 §3.5 ``slow_down`` (interval += 5),
        ``authorization_pending`` (continue), and ``expired_token`` /
        ``access_denied`` (abort).
        """
        interval = device.interval
        deadline = time.time() + device.expires_in
        endpoint = f"https://{self.domain}/oauth/token"

        while True:
            now = time.time()
            if now >= deadline:
                raise DeviceFlowError(
                    "expired_token",
                    "device code expired before the operator approved",
                )
            self._sleep(interval)
            try:
                response = self._client().post(
                    endpoint,
                    data={
                        "grant_type": GRANT_TYPE_DEVICE_CODE,
                        "device_code": device.device_code,
                        "client_id": self.client_id,
                    },
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
            except httpx.HTTPError as exc:
                # Transient network failure — keep polling. Honour the
                # current interval; do NOT back off further so we
                # don't drift past the device-code deadline.
                logger.warning(
                    "DeviceFlowClient transient error (%s); will retry",
                    exc.__class__.__name__,
                )
                continue

            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise DeviceFlowError(
                        "invalid_response",
                        "token endpoint returned non-JSON",
                    ) from exc
                access_token = payload.get("access_token")
                if not isinstance(access_token, str) or not access_token:
                    raise DeviceFlowError(
                        "invalid_response",
                        "token endpoint response missing access_token",
                    )
                return DeviceFlowTokens(
                    access_token=access_token,
                    token_type=str(payload.get("token_type") or "Bearer"),
                    expires_in=int(payload.get("expires_in", 3600)),
                    refresh_token=payload.get("refresh_token"),
                    id_token=payload.get("id_token"),
                    scope=payload.get("scope"),
                    raw=dict(payload),
                )

            # Non-200 — parse the OAuth error envelope per RFC 8628 §3.5.
            code, description = self._parse_error_payload(response)
            if code == "authorization_pending":
                continue
            if code == "slow_down":
                interval += 5
                logger.debug("DeviceFlowClient slow_down; interval=%ds", interval)
                continue
            if code in ("expired_token", "access_denied"):
                raise DeviceFlowError(code, description)
            raise DeviceFlowError(code or "unknown_error", description)

    def login(
        self,
        *,
        scope: str,
        organization: str | None = None,
        resource: str | None = None,
        open_browser: bool = True,
        extra_params: dict[str, str] | None = None,
    ) -> DeviceFlowTokens:
        """End-to-end Device Authorization Grant.

        Announces the verification URI + user code to the operator
        (printed to stdout via the ``announce_fn`` constructor hook),
        optionally opens the browser, then polls until the IdP
        returns tokens.
        """
        device = self.request_device_code(
            scope=scope,
            organization=organization,
            resource=resource,
            extra_params=extra_params,
        )
        complete = device.verification_uri_complete or device.verification_uri

        self._announce("")
        self._announce("To authorise the AQP CLI:")
        self._announce(f"  1. Open this URL on any device:  {complete}")
        if device.verification_uri_complete:
            self._announce(f"     (or open {device.verification_uri} and enter the code)")
        self._announce(f"  2. Confirm that the code displayed matches:  {device.user_code}")
        self._announce(f"  3. The CLI will continue automatically (expires in {device.expires_in}s).")
        self._announce("")

        if open_browser:
            try:
                self._open_browser(complete)
            except Exception:  # noqa: BLE001
                # Browser auto-open is best-effort; the printed URL
                # is always the authoritative path.
                pass

        return self.poll_for_tokens(device)

    def refresh(self, refresh_token: str) -> DeviceFlowTokens:
        """Exchange a refresh token for a fresh access token.

        Mirrors :class:`DeviceFlowTokens` shape so callers don't need
        to branch on which method minted the tokens.
        """
        endpoint = f"https://{self.domain}/oauth/token"
        response = self._client().post(
            endpoint,
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "refresh_token": refresh_token,
            },
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        if response.status_code != 200:
            raise self._error_from_response(response, default_code="refresh_failed")
        try:
            payload = response.json()
        except ValueError as exc:
            raise DeviceFlowError("invalid_response", "refresh returned non-JSON") from exc
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise DeviceFlowError(
                "invalid_response",
                "refresh response missing access_token",
            )
        return DeviceFlowTokens(
            access_token=access_token,
            token_type=str(payload.get("token_type") or "Bearer"),
            expires_in=int(payload.get("expires_in", 3600)),
            # Refresh-token rotation: Auth0 returns a NEW refresh_token;
            # fall back to the original when the server doesn't rotate.
            refresh_token=payload.get("refresh_token") or refresh_token,
            id_token=payload.get("id_token"),
            scope=payload.get("scope"),
            raw=dict(payload),
        )

    def close(self) -> None:
        if self._owns_http and self._http is not None:
            try:
                self._http.close()
            finally:
                self._http = None

    # -- internals -------------------------------------------------------

    def _client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=self._timeout)
        return self._http

    @staticmethod
    def _parse_error_payload(response: httpx.Response) -> tuple[str, str | None]:
        try:
            payload = response.json()
        except ValueError:
            return "unknown_error", response.text or None
        code = str(payload.get("error") or "unknown_error")
        description = payload.get("error_description")
        if description is None:
            description = response.text or None
        return code, description

    @staticmethod
    def _error_from_response(
        response: httpx.Response,
        *,
        default_code: str,
    ) -> DeviceFlowError:
        code, description = DeviceFlowClient._parse_error_payload(response)
        if not code or code == "unknown_error":
            code = default_code
        return DeviceFlowError(code, description)


def _default_open_browser(url: str) -> bool:
    """Best-effort browser launcher.

    Returns ``True`` on success; never raises. The CLI prints the URL
    regardless so a failed browser open is always recoverable.
    """
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


__all__ = [
    "DeviceAuthorizationResponse",
    "DeviceFlowCancelled",
    "DeviceFlowClient",
    "DeviceFlowError",
    "DeviceFlowTokens",
    "GRANT_TYPE_DEVICE_CODE",
]
