"""REST adapter base with rate limiting + retry.

Reusable HTTP client primitives for venue REST APIs. Concrete adapters
(e.g. Coinbase, Alpaca paper REST, Kraken) subclass to get authenticated
HTTP with rate-limit-aware retry out of the box.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RestAdapterError(RuntimeError):
    """Raised on terminal REST failure (after retries exhausted)."""


class RestAdapterBase:
    """Shared HTTP/REST plumbing.

    Per AGENTS hard rule 26 (credentials), the adapter resolves
    venue API keys via :class:`aqp.credentials.CredentialResolver`
    rather than reading ``settings.*_token`` directly.
    """

    def __init__(
        self,
        *,
        base_url: str,
        max_requests_per_second: float | None = None,
        max_retries: int = 3,
        timeout_seconds: float = 30.0,
        credential_alias: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._max_rps = max_requests_per_second
        self._max_retries = max_retries
        self._timeout = timeout_seconds
        self._credential_alias = credential_alias
        self._client: Any | None = None
        self._limiter: Any | None = None
        self._auth_headers: dict[str, str] = {}

    async def connect(self) -> None:
        """Initialise the underlying httpx client + rate limiter."""
        try:
            import httpx  # noqa: F401
        except ImportError as exc:
            raise RestAdapterError("httpx required for RestAdapterBase") from exc
        import httpx

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self._timeout,
        )
        if self._max_rps is not None:
            try:
                from aiolimiter import AsyncLimiter  # type: ignore[import-not-found]

                self._limiter = AsyncLimiter(max_rate=self._max_rps, time_period=1.0)
            except ImportError:
                logger.warning(
                    "aiolimiter not installed; %s will not rate-limit",
                    self.__class__.__name__,
                )
        if self._credential_alias:
            await self._load_credentials()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _load_credentials(self) -> None:
        """Resolve API keys through :class:`CredentialResolver`."""
        try:
            from aqp.credentials.resolver import CredentialResolver  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001
            return
        try:
            resolver = CredentialResolver()
            creds = await resolver.resolve(alias=self._credential_alias)  # type: ignore[attr-defined]
            if isinstance(creds, dict):
                token = creds.get("api_key") or creds.get("token")
                if token:
                    self._auth_headers["Authorization"] = f"Bearer {token}"
        except Exception:  # noqa: BLE001
            logger.debug(
                "CredentialResolver failed for %s", self._credential_alias, exc_info=True
            )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Issue an HTTP request with rate limiting + retry.

        Returns the decoded JSON body.  Raises :class:`RestAdapterError`
        after all retries are exhausted.
        """
        if self._client is None:
            await self.connect()
        assert self._client is not None

        try:
            from tenacity import (  # type: ignore[import-not-found]
                AsyncRetrying,
                retry_if_exception_type,
                stop_after_attempt,
                wait_exponential,
            )
        except ImportError:
            AsyncRetrying = None  # type: ignore[assignment]

        merged_headers = {**self._auth_headers, **(headers or {})}

        async def _do_request() -> dict[str, Any]:
            if self._limiter is not None:
                async with self._limiter:
                    resp = await self._client.request(  # type: ignore[union-attr]
                        method, path, json=json, params=params, headers=merged_headers
                    )
            else:
                resp = await self._client.request(  # type: ignore[union-attr]
                    method, path, json=json, params=params, headers=merged_headers
                )
            resp.raise_for_status()
            return resp.json()

        if AsyncRetrying is None:
            try:
                return await _do_request()
            except Exception as exc:  # noqa: BLE001
                raise RestAdapterError(str(exc)) from exc

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._max_retries),
                wait=wait_exponential(multiplier=0.5, max=10.0),
                retry=retry_if_exception_type(Exception),
                reraise=True,
            ):
                with attempt:
                    return await _do_request()
        except Exception as exc:  # noqa: BLE001
            raise RestAdapterError(str(exc)) from exc
        raise RestAdapterError("retries exhausted")


__all__ = ["RestAdapterBase", "RestAdapterError"]
