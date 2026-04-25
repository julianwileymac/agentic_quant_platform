"""Shared brokerage helpers: base class, retry, rate-limit, tracing."""
from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from aqp.core.interfaces import IAsyncBrokerage, IBrokerage
from aqp.core.types import AccountData, OrderData, OrderRequest, PositionData
from aqp.observability import get_tracer

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token-bucket style async rate-limiter (calls per second)."""

    def __init__(self, calls_per_second: float) -> None:
        self.calls_per_second = max(0.001, float(calls_per_second))
        self._min_interval = 1.0 / self.calls_per_second
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            elapsed = time.monotonic() - self._last_call
            wait = self._min_interval - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()


def traced_broker_call(span_name: str, *, venue: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that wraps a broker method in an OTel span + error logging.

    Works on both sync and async callables.
    """
    tracer = get_tracer("aqp.broker")

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with tracer.start_as_current_span(span_name) as span:
                    span.set_attribute("broker.venue", venue)
                    try:
                        result = await fn(*args, **kwargs)
                        return result
                    except Exception as exc:  # noqa: BLE001
                        span.record_exception(exc)
                        logger.exception("%s (%s) failed", span_name, venue)
                        raise

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("broker.venue", venue)
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    span.record_exception(exc)
                    logger.exception("%s (%s) failed", span_name, venue)
                    raise

        return sync_wrapper

    return decorator


class BaseAsyncBrokerage(IBrokerage, IAsyncBrokerage):
    """Common plumbing: connection state, rate-limit, shared helpers.

    Subclasses implement ``_connect_impl``, ``_submit_order_impl``,
    ``_cancel_order_impl``, ``_query_positions_impl``, ``_query_account_impl``
    (all ``async``) and optionally ``stream_order_updates``.
    """

    name: str = "base"
    rate_limit_per_second: float = 5.0

    def __init__(self) -> None:
        self._connected = False
        self._rate_limiter = RateLimiter(self.rate_limit_per_second)
        self._order_event_queue: asyncio.Queue[OrderData] = asyncio.Queue()

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ---------------------------- async interface ------------------------

    async def connect_async(self) -> None:
        if self._connected:
            return
        await self._connect_impl()
        self._connected = True
        logger.info("%s brokerage connected", self.name)

    async def disconnect_async(self) -> None:
        if not self._connected:
            return
        try:
            await self._disconnect_impl()
        finally:
            self._connected = False
            logger.info("%s brokerage disconnected", self.name)

    async def submit_order_async(self, request: OrderRequest) -> OrderData:
        await self._rate_limiter.wait()
        return await self._submit_order_impl(request)

    async def cancel_order_async(self, order_id: str) -> bool:
        await self._rate_limiter.wait()
        return await self._cancel_order_impl(order_id)

    async def query_positions_async(self) -> list[PositionData]:
        return await self._query_positions_impl()

    async def query_account_async(self) -> AccountData:
        return await self._query_account_impl()

    async def stream_order_updates(self) -> AsyncIterator[OrderData]:
        while self._connected:
            try:
                yield await asyncio.wait_for(self._order_event_queue.get(), timeout=1.0)
            except TimeoutError:
                continue

    # ---------------------------- sync bridge ----------------------------

    def connect(self) -> None:
        _run_sync(self.connect_async())

    def disconnect(self) -> None:
        _run_sync(self.disconnect_async())

    def submit_order(self, request: OrderRequest) -> OrderData:
        return _run_sync(self.submit_order_async(request))

    def cancel_order(self, order_id: str) -> bool:
        return _run_sync(self.cancel_order_async(order_id))

    def query_positions(self) -> list[PositionData]:
        return _run_sync(self.query_positions_async())

    def query_account(self) -> AccountData:
        return _run_sync(self.query_account_async())

    # ---------------------------- hooks ----------------------------------

    async def _connect_impl(self) -> None:  # pragma: no cover — abstract
        raise NotImplementedError

    async def _disconnect_impl(self) -> None:  # pragma: no cover — abstract
        raise NotImplementedError

    async def _submit_order_impl(self, request: OrderRequest) -> OrderData:
        raise NotImplementedError

    async def _cancel_order_impl(self, order_id: str) -> bool:
        raise NotImplementedError

    async def _query_positions_impl(self) -> list[PositionData]:
        raise NotImplementedError

    async def _query_account_impl(self) -> AccountData:
        raise NotImplementedError


def _run_sync(coro: Any) -> Any:
    """Run an awaitable to completion from sync code.

    Handles three cases:
    - no event loop → ``asyncio.run``
    - loop running in another thread → block on ``asyncio.run_coroutine_threadsafe``
    - loop running in current thread (Jupyter) → raise, since that would
      deadlock; callers should use the ``*_async`` variant directly.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return asyncio.run(coro)
    if loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()
    return loop.run_until_complete(coro)
