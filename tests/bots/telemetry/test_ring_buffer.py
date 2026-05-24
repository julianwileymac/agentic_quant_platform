"""Phase 7: SPSC ring buffer correctness (pure-Python fallback)."""
from __future__ import annotations

import pytest

from aqp_bots.hft.ring_buffer import BufferFull, SPSCRingBuffer


def test_push_pop_single() -> None:
    rb = SPSCRingBuffer(capacity=4)
    rb.push_nowait("a")
    assert rb.pop_nowait() == "a"
    assert rb.pop_nowait() is None


def test_capacity_must_be_power_of_two() -> None:
    with pytest.raises(ValueError):
        SPSCRingBuffer(capacity=3)


def test_buffer_full_raises() -> None:
    rb = SPSCRingBuffer(capacity=2)
    rb.push_nowait("a")
    rb.push_nowait("b")
    with pytest.raises((BufferFull, RuntimeError)):
        rb.push_nowait("c")


def test_fifo_order() -> None:
    rb = SPSCRingBuffer(capacity=8)
    for i in range(5):
        rb.push_nowait(i)
    out = []
    while True:
        v = rb.pop_nowait()
        if v is None:
            break
        out.append(v)
    assert out == [0, 1, 2, 3, 4]


def test_wrap_around_after_drain() -> None:
    rb = SPSCRingBuffer(capacity=4)
    for i in range(3):
        rb.push_nowait(i)
    for _ in range(3):
        rb.pop_nowait()
    # All slots free; should accept another full batch.
    for i in range(4):
        rb.push_nowait(100 + i)
    assert len(rb) == 4


def test_is_empty() -> None:
    rb = SPSCRingBuffer(capacity=2)
    assert rb.is_empty()
    rb.push_nowait("x")
    assert not rb.is_empty()
    rb.pop_nowait()
    assert rb.is_empty()
