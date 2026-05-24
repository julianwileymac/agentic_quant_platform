# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""Cython SPSC ring buffer (LMAX Disruptor expressed in Python).

Single-producer/single-consumer fixed-size circular buffer with
power-of-two capacity. Tail and head are 64-bit unsigned counters;
indices are computed via ``head & mask`` / ``tail & mask`` which is
free on x86_64.

No locks on the hot path — under the CPython GIL the increment +
read is atomic between coroutines on the same thread; cross-thread
single-producer/single-consumer semantics rely on the GIL ordering
guarantee for ``cdef`` ints.

Build:

    cythonize -i aqp_bots/hft/_ring_buffer_cy.pyx

(the ``[hft]`` extra in pyproject.toml triggers this automatically
when the wheel is built with hatch-cython).
"""

from libc.stdint cimport uint64_t


cdef class SPSCRingBuffer:
    """Cython SPSC ring buffer.

    Drops in for :class:`aqp_bots.hft.ring_buffer._PythonSPSCRingBuffer`
    with identical surface.
    """

    cdef:
        list _buf
        uint64_t _head
        uint64_t _tail
        uint64_t _capacity
        uint64_t _mask

    def __cinit__(self, capacity: int) -> None:
        if capacity < 2 or (capacity & (capacity - 1)) != 0:
            raise ValueError("capacity must be a power of two >= 2")
        self._capacity = <uint64_t>capacity
        self._mask = <uint64_t>(capacity - 1)
        self._buf = [None] * capacity
        self._head = 0
        self._tail = 0

    cpdef push_nowait(self, object item):
        cdef uint64_t next_tail = self._tail + 1
        if next_tail - self._head > self._capacity:
            raise RuntimeError(f"SPSCRingBuffer full ({self._capacity})")
        self._buf[<Py_ssize_t>(self._tail & self._mask)] = item
        self._tail = next_tail

    cpdef object pop_nowait(self):
        cdef object item
        if self._head == self._tail:
            return None
        item = self._buf[<Py_ssize_t>(self._head & self._mask)]
        self._buf[<Py_ssize_t>(self._head & self._mask)] = None
        self._head += 1
        return item

    cpdef bint is_empty(self):
        return self._head == self._tail

    def __len__(self) -> int:
        return <Py_ssize_t>(self._tail - self._head)

    @property
    def capacity(self) -> int:
        return <Py_ssize_t>self._capacity
