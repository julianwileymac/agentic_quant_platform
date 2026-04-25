"""Generic async REST brokerage base class.

Concrete providers (Tradier, OANDA, Binance, ...) subclass this and implement
a handful of small translation methods. The heavy lifting (auth headers,
retries, rate-limits, OTel spans, polling for order updates) lives here so
new providers can be added in ~50 lines.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from aqp.core.types import (
    AccountData,
    OrderData,
    OrderRequest,
    PositionData,
)
from aqp.trading.brokerages.base import BaseAsyncBrokerage, traced_broker_call

logger = logging.getLogger(__name__)


class _TransientHTTPError(Exception):
    """Flag transient HTTP errors for tenacity retry."""


class RestBrokerage(BaseAsyncBrokerage):
    """Shared plumbing for bearer-token OAuth REST brokers."""

    name = "rest"
    base_url: str = ""
    rate_limit_per_second = 5.0
    order_poll_interval_seconds: float = 2.0

    def __init__(
        self,
        token: str,
        base_url: str | None = None,
        account_id: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        super().__init__()
        if not token:
            raise ValueError(f"{self.name} brokerage requires an API token")
        self.token = token
        self.base_url = (base_url or self.base_url).rstrip("/")
        self.account_id = account_id or ""
        self._timeout = float(timeout)
        self._client: httpx.AsyncClient | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._seen_orders: dict[str, OrderData] = {}

    # -------------------------------- lifecycle --------------------------

    async def _connect_impl(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._auth_headers(),
            timeout=self._timeout,
        )
        # Sanity check the session (subclasses may override).
        await self._query_account_impl()
        self._poll_task = asyncio.create_task(self._poll_order_updates())

    async def _disconnect_impl(self) -> None:
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._poll_task
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # -------------------------------- overridable auth/URL ---------------

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    # -------------------------------- HTTP primitives --------------------

    @retry(
        wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(_TransientHTTPError),
        reraise=True,
    )
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> Any:
        assert self._client is not None, "call connect_async() first"
        try:
            response = await self._client.request(
                method,
                path,
                params=params,
                data=data,
                json=json_body,
            )
        except httpx.TransportError as exc:
            raise _TransientHTTPError(str(exc)) from exc
        if response.status_code in {429, 502, 503, 504}:
            raise _TransientHTTPError(f"{response.status_code} from {path}")
        response.raise_for_status()
        return response.json()

    # -------------------------------- order ops --------------------------

    @traced_broker_call("broker.submit_order", venue="rest")
    async def _submit_order_impl(self, request: OrderRequest) -> OrderData:
        body = self._order_payload(request)
        raw = await self._request(
            "POST",
            self._orders_path(),
            data=body if self._send_form_encoded() else None,
            json_body=None if self._send_form_encoded() else body,
        )
        order = self._parse_order(raw, request=request)
        self._seen_orders[order.order_id] = order
        return order

    @traced_broker_call("broker.cancel_order", venue="rest")
    async def _cancel_order_impl(self, order_id: str) -> bool:
        try:
            await self._request("DELETE", self._order_detail_path(order_id))
            return True
        except httpx.HTTPStatusError:
            logger.exception("REST cancel failed")
            return False

    @traced_broker_call("broker.query_positions", venue="rest")
    async def _query_positions_impl(self) -> list[PositionData]:
        raw = await self._request("GET", self._positions_path())
        return self._parse_positions(raw)

    @traced_broker_call("broker.query_account", venue="rest")
    async def _query_account_impl(self) -> AccountData:
        raw = await self._request("GET", self._account_path())
        return self._parse_account(raw)

    # -------------------------------- polling ----------------------------

    async def _poll_order_updates(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.order_poll_interval_seconds)
                raw = await self._request("GET", self._orders_path())
                for order in self._parse_orders(raw):
                    cached = self._seen_orders.get(order.order_id)
                    if cached is None or cached.status != order.status or cached.filled_quantity != order.filled_quantity:
                        self._seen_orders[order.order_id] = order
                        await self._order_event_queue.put(order)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("poll_order_updates error")
                await asyncio.sleep(self.order_poll_interval_seconds)

    # -------------------------------- subclass hooks ---------------------

    def _orders_path(self) -> str:
        raise NotImplementedError

    def _order_detail_path(self, order_id: str) -> str:
        raise NotImplementedError

    def _positions_path(self) -> str:
        raise NotImplementedError

    def _account_path(self) -> str:
        raise NotImplementedError

    def _order_payload(self, request: OrderRequest) -> dict[str, Any]:
        raise NotImplementedError

    def _send_form_encoded(self) -> bool:
        return False

    def _parse_order(self, raw: Any, *, request: OrderRequest | None = None) -> OrderData:
        raise NotImplementedError

    def _parse_orders(self, raw: Any) -> list[OrderData]:
        raise NotImplementedError

    def _parse_positions(self, raw: Any) -> list[PositionData]:
        raise NotImplementedError

    def _parse_account(self, raw: Any) -> AccountData:
        raise NotImplementedError

    # -------------------------------- time helper ------------------------

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(tz=UTC).replace(tzinfo=None)
