"""Rust extension escape hatch for sub-100µs paths.

Plan caveat #1 (Python ceiling): pure Python + Cython targets 100-500µs
for non-kernel-bypass HFT. Bots requiring sub-100µs MUST drop to a
Rust extension built with PyO3.

This module provides the **boundary** — the Python-side interface that
the optional Rust extension implements. When the Rust wheel
(``aqp_bots_hft_rs``) isn't installed every function returns a clear
:class:`RustEscapeHatchUnavailable` error so callers can fall back to
the Cython path gracefully.

To build the Rust crate (out of band of this Python package)::

    cd aqp_bots/hft_rs
    maturin build --release
    pip install target/wheels/aqp_bots_hft_rs-*.whl

The crate is *intentionally* not pinned in pyproject.toml — building
it requires a Rust toolchain that we don't want to mandate for every
dev environment.
"""
from __future__ import annotations


class RustEscapeHatchUnavailable(RuntimeError):
    """Raised when a sub-100µs operation is requested but no Rust ext present."""


def _try_import_rs() -> object | None:
    try:
        import aqp_bots_hft_rs  # type: ignore[import-not-found]

        return aqp_bots_hft_rs
    except ImportError:
        return None


_RS = _try_import_rs()


def rust_available() -> bool:
    """Return True iff the optional Rust extension is importable."""
    return _RS is not None


def ring_buffer_rs(capacity: int) -> object:
    """Construct a Rust-backed SPSC ring buffer.

    Falls back to :class:`RustEscapeHatchUnavailable` when the crate
    isn't installed; callers should catch that and use the Cython
    :class:`SPSCRingBuffer` instead.
    """
    if _RS is None:
        raise RustEscapeHatchUnavailable(
            "aqp_bots_hft_rs not installed; sub-100µs SPSC requires the Rust extension"
        )
    return _RS.RingBuffer(capacity)  # type: ignore[attr-defined]


def order_book_rs() -> object:
    """Construct a Rust-backed Level-2 order book.

    For full-depth book maintenance at 100k+ updates/s/symbol.
    """
    if _RS is None:
        raise RustEscapeHatchUnavailable(
            "aqp_bots_hft_rs not installed; full-depth order book requires Rust"
        )
    return _RS.OrderBook()  # type: ignore[attr-defined]


__all__ = [
    "RustEscapeHatchUnavailable",
    "order_book_rs",
    "ring_buffer_rs",
    "rust_available",
]
