"""Pricing futures -- async result handles for distributed dispatch.

When the active :class:`PricingContext` is in ``celery`` mode, the
:func:`calc` dispatch returns a :class:`PricingFuture` rather than
a value. The future resolves either synchronously via
:meth:`PricingFuture.result` or asynchronously via
:meth:`PricingFuture.aresult`.

:class:`CompositeResultFuture` aggregates many futures into one
gather-style await; used when a portfolio risk calc fans out
hundreds of per-instrument tasks.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PricingFuture:
    """Handle to an in-flight pricing calc.

    Wraps either:

    * a synchronous already-computed result (``mode='sync'``) -- the
      ``result()`` call returns immediately
    * an async coroutine (``mode='async'``) -- ``aresult()`` awaits it
    * a Celery :class:`celery.result.AsyncResult` (``mode='celery'``)
      -- ``result()`` blocks polling, ``aresult()`` polls cooperatively
    """

    mode: str = "sync"
    measure: str | None = None
    instrument_ref: Any = None
    value: Any = None
    error: str | None = None
    started_at: float = field(default_factory=time.monotonic)
    elapsed_ms: float = 0.0
    # Celery / asyncio bridges
    _async_result: Any = None  # celery AsyncResult
    _coro: Any = None  # asyncio coroutine

    def result(self, timeout: float | None = None) -> Any:
        """Block until the result is available; return it (or raise on error).

        For sync mode this returns immediately. For async coroutine
        mode, runs the coroutine to completion via
        ``asyncio.run``; only safe outside an active event loop.
        For Celery mode, polls the :class:`AsyncResult`.
        """
        if self.error is not None:
            raise RuntimeError(self.error)
        if self.mode == "sync":
            return self.value
        if self.mode == "celery" and self._async_result is not None:
            value = self._async_result.get(timeout=timeout)
            self.value = value
            self.elapsed_ms = (time.monotonic() - self.started_at) * 1000.0
            return value
        if self.mode == "async" and self._coro is not None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is None:
                value = asyncio.run(self._coro)
            else:
                # We're inside a running loop -- cannot block here.
                raise RuntimeError(
                    "PricingFuture.result() inside an event loop; use aresult()"
                )
            self.value = value
            self.elapsed_ms = (time.monotonic() - self.started_at) * 1000.0
            return value
        return self.value

    async def aresult(self, timeout: float | None = None) -> Any:
        """Async-await for the result.

        For sync mode returns immediately. For async coroutine, awaits
        it directly. For Celery, polls cooperatively at 50ms intervals.
        """
        if self.error is not None:
            raise RuntimeError(self.error)
        if self.mode == "sync":
            return self.value
        if self.mode == "async" and self._coro is not None:
            value = await self._coro
            self.value = value
            self.elapsed_ms = (time.monotonic() - self.started_at) * 1000.0
            return value
        if self.mode == "celery" and self._async_result is not None:
            deadline = time.monotonic() + (timeout or 1e9)
            while not self._async_result.ready():
                if time.monotonic() > deadline:
                    raise TimeoutError("PricingFuture.aresult timed out")
                await asyncio.sleep(0.05)
            value = self._async_result.get()
            self.value = value
            self.elapsed_ms = (time.monotonic() - self.started_at) * 1000.0
            return value
        return self.value

    def done(self) -> bool:
        if self.mode == "sync":
            return True
        if self.mode == "celery" and self._async_result is not None:
            return bool(self._async_result.ready())
        if self.mode == "async" and self._coro is not None:
            # Coroutines aren't easily introspected; return True only
            # after a successful awaited resolution.
            return self.value is not None or self.error is not None
        return self.value is not None or self.error is not None


@dataclass
class CompositeResultFuture:
    """Wrap a list of :class:`PricingFuture` into a single gather handle.

    Used when a portfolio calc fans out one task per instrument or per
    risk measure and the caller wants to ``await all_done()`` once.
    """

    futures: list[PricingFuture] = field(default_factory=list)

    def add(self, future: PricingFuture) -> None:
        self.futures.append(future)

    def results(self, timeout: float | None = None) -> list[Any]:
        return [f.result(timeout=timeout) for f in self.futures]

    async def aresults(self, timeout: float | None = None) -> list[Any]:
        return await asyncio.gather(
            *(f.aresult(timeout=timeout) for f in self.futures)
        )

    def __iter__(self):
        return iter(self.futures)

    def __len__(self) -> int:
        return len(self.futures)


__all__ = [
    "CompositeResultFuture",
    "PricingFuture",
]
