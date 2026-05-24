"""SPSC ring buffer — LMAX Disruptor pattern.

Single-producer/single-consumer queue with no locks on the hot path.
The Disruptor pattern (Martin Fowler, *The LMAX Architecture*) is the
canonical sub-millisecond messaging primitive; we implement it here in
pure Python with a Cython fast-path planned for the ``[hft]`` extra.

When the Cython extension at ``aqp_bots/hft/_ring_buffer_cy.pyx`` is
built and importable this module re-exports it; otherwise the pure-
Python implementation below provides identical semantics at lower
throughput (still good for mid-frequency bots).

Public API::

    rb = SPSCRingBuffer(capacity=4096)
    rb.push_nowait(msg)        # raises BufferFull if full
    msg = rb.pop_nowait()      # returns None if empty
    rb.is_empty()
    len(rb)
"""
from __future__ import annotations

import threading
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class BufferFull(RuntimeError):
    """Raised when ``push_nowait`` is called on a full ring."""


class _PythonSPSCRingBuffer(Generic[T]):
    """Pure-Python fallback ring buffer.

    Single producer + single consumer; safe under the CPython GIL
    without explicit locks. For multi-producer / multi-consumer use,
    fall back to :class:`asyncio.Queue` or :class:`queue.Queue`.

    The Cython build target replaces this class with a lock-free
    implementation backed by ``numpy.uint64`` head/tail counters and
    a fixed-size object array; we emulate the surface here.
    """

    def __init__(self, *, capacity: int) -> None:
        if capacity < 2 or (capacity & (capacity - 1)) != 0:
            raise ValueError("capacity must be a power of two >= 2")
        self._capacity = capacity
        self._mask = capacity - 1
        self._buf: list[Any] = [None] * capacity
        self._head: int = 0  # next read index
        self._tail: int = 0  # next write index
        self._lock = threading.Lock()  # CPython GIL is enough but lock is cheap insurance

    def push_nowait(self, item: T) -> None:
        with self._lock:
            next_tail = self._tail + 1
            if next_tail - self._head > self._capacity:
                raise BufferFull(
                    f"SPSCRingBuffer full ({self._capacity})"
                )
            self._buf[self._tail & self._mask] = item
            self._tail = next_tail

    def pop_nowait(self) -> T | None:
        with self._lock:
            if self._head == self._tail:
                return None
            item = self._buf[self._head & self._mask]
            self._buf[self._head & self._mask] = None
            self._head += 1
            return item

    def is_empty(self) -> bool:
        return self._head == self._tail

    def __len__(self) -> int:
        return self._tail - self._head

    @property
    def capacity(self) -> int:
        return self._capacity


# Prefer the Cython extension when built; otherwise fall back.
try:
    from aqp_bots.hft._ring_buffer_cy import (  # type: ignore[import-not-found]
        SPSCRingBuffer as _CythonSPSCRingBuffer,
    )

    SPSCRingBuffer: type = _CythonSPSCRingBuffer
except Exception:  # noqa: BLE001
    SPSCRingBuffer = _PythonSPSCRingBuffer  # type: ignore[misc,assignment]


__all__ = ["BufferFull", "SPSCRingBuffer"]
