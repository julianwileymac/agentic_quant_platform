"""HFT hot-path primitives.

Six modules:

- :mod:`aqp_bots.hft.ring_buffer` — Cython single-producer/single-consumer
  ring buffer (LMAX Disruptor expressed in Python). Falls back to a
  pure-Python implementation when the Cython extension isn't built.
- :mod:`aqp_bots.hft.ptp_clock` — PTP-disciplined wall clock
  (IEEE 1588) wired through ``ptp4l`` + ``phc2sys``. Mandatory for
  HFT bots (RTS 25 1-microsecond timestamp granularity).
- :mod:`aqp_bots.hft.numa` — NUMA topology discovery and pinning
  helpers.
- :mod:`aqp_bots.hft.hugepages` — HugePages allocator interface.
- :mod:`aqp_bots.hft.sr_iov` — SR-IOV NIC awareness.
- :mod:`aqp_bots.hft.microsecond_spans` — microsecond OTel span
  bridging into the SPSC ring.
- :mod:`aqp_bots.hft.escape_hatch` — Rust extension boundary (PyO3)
  for sub-100µs paths.

Empirical anchor: Adaptive's Aeron / Google Cloud benchmark
(weareadaptive.com, 21 Feb 2024) reports 57µs default / 18µs with
kernel-bypass at 100k msg/s — Java baseline. Python+Cython target is
100-500µs for non-kernel-bypass; sub-100µs MUST use the Rust escape
hatch (see :mod:`aqp_bots.hft.escape_hatch`).
"""
from __future__ import annotations

from aqp_bots.hft.hugepages import HugePagesAllocator, hugepages_available
from aqp_bots.hft.numa import (
    NumaPinHint,
    NumaTopology,
    discover_topology,
    pin_to_node,
)
from aqp_bots.hft.ring_buffer import SPSCRingBuffer
from aqp_bots.hft.sr_iov import SrIovDevice, list_sr_iov_devices

__all__ = [
    "HugePagesAllocator",
    "NumaPinHint",
    "NumaTopology",
    "SPSCRingBuffer",
    "SrIovDevice",
    "discover_topology",
    "hugepages_available",
    "list_sr_iov_devices",
    "pin_to_node",
]
