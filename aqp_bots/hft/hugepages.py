"""HugePages allocator + availability check.

HFT bots benefit from HugePages for two reasons (blueprint §F.3):

1. Reduced TLB misses on hot-path memory accesses (order book arrays,
   PnL aggregations, ML inference tensors).
2. Page locking — preventing the kernel from swapping out the order
   book under memory pressure.

The Pod requests HugePages via the ``resources.requests.hugepages-2Mi``
field; the operator's renderer (Phase 8) reads
:attr:`CapabilitySpec.needs_hugepages_mib` and emits that field.

This module exposes a small allocator over ``mmap`` with
``MAP_HUGETLB`` for processes that need to manage HugePages
explicitly inside the bot (rare; usually the kernel allocator
handles it via the Pod's HugePages quota).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


_HUGEPAGES_NR_PATH = Path("/sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages")


def hugepages_available() -> bool:
    """Return True iff the host has any 2 MiB hugepages configured."""
    if sys.platform != "linux":
        return False
    if not _HUGEPAGES_NR_PATH.exists():
        return False
    try:
        return int(_HUGEPAGES_NR_PATH.read_text().strip()) > 0
    except (OSError, ValueError):
        return False


def hugepages_total_count() -> int:
    """Return the total 2 MiB hugepages configured on the host."""
    try:
        return int(_HUGEPAGES_NR_PATH.read_text().strip())
    except (OSError, ValueError):
        return 0


class HugePagesAllocator:
    """Thin wrapper for ``mmap`` with ``MAP_HUGETLB``.

    Intended for bots that need a single large, page-locked region —
    e.g. a 16 MiB order-book array, or a 64 MiB shared-memory ring for
    the HFT OTel span buffer.

    Falls back to a regular ``mmap`` allocation on non-Linux platforms
    or when no hugepages are configured — useful so dev environments
    still run, just without the perf benefit.
    """

    def __init__(self, *, size_bytes: int) -> None:
        if size_bytes <= 0:
            raise ValueError("size_bytes must be > 0")
        self.size_bytes = size_bytes
        self._mmap: object | None = None

    def allocate(self) -> object:
        """Allocate the region. Returns the underlying mmap object."""
        import mmap

        flags = mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS  # type: ignore[attr-defined]
        if hugepages_available() and hasattr(mmap, "MAP_HUGETLB"):
            flags |= getattr(mmap, "MAP_HUGETLB", 0)  # type: ignore[arg-type]
        try:
            self._mmap = mmap.mmap(
                -1,
                self.size_bytes,
                flags=flags,
                prot=mmap.PROT_READ | mmap.PROT_WRITE,
            )
        except (OSError, ValueError):
            # Fall back to plain mmap without MAP_HUGETLB.
            self._mmap = mmap.mmap(
                -1,
                self.size_bytes,
                flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS,  # type: ignore[attr-defined]
                prot=mmap.PROT_READ | mmap.PROT_WRITE,
            )
        return self._mmap

    def close(self) -> None:
        if self._mmap is not None:
            try:
                self._mmap.close()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
            self._mmap = None


__all__ = [
    "HugePagesAllocator",
    "hugepages_available",
    "hugepages_total_count",
]
