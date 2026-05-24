"""Microsecond-precision OpenTelemetry span helper.

Wraps a normal OTel span with explicit ``monotonic_ns`` start/end
recording so the tick-to-trade latency histogram in
:mod:`aqp_bots.telemetry.metrics` is fed a precise duration even when
the upstream SDK is using millisecond-precision internal clocks.

Usage::

    with hft_span(tracer, "tick_to_trade", attributes={"venue": "cme"}) as span:
        # ... fast-path work ...
        pass
    # span.duration_ns is now available; the histogram has been observed.

The helper additionally pushes the span's start/end nanoseconds onto
the lock-free :class:`SPSCRingBuffer` from
:mod:`aqp_bots.hft.ring_buffer` so the exporter thread can drain them
to the OTel Collector via shared-memory IPC (blueprint §J.2).
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

from aqp_bots.hft.ring_buffer import SPSCRingBuffer


# Module-level ring buffer; the exporter (HFTSpanProcessor) drains it.
_MICRO_RING: SPSCRingBuffer | None = None


def _get_ring(capacity: int = 16384) -> SPSCRingBuffer:
    global _MICRO_RING
    if _MICRO_RING is None:
        _MICRO_RING = SPSCRingBuffer(capacity=capacity)
    return _MICRO_RING


def get_microsecond_ring() -> SPSCRingBuffer:
    """Return the process-wide ring buffer (lazy)."""
    return _get_ring()


@contextmanager
def hft_span(
    tracer: Any,
    name: str,
    *,
    attributes: dict[str, Any] | None = None,
    record_in_histogram: bool = True,
) -> Iterator[Any]:
    """Open an OTel span with microsecond-precision duration tracking.

    The wrapped span behaves like any OTel span; in addition:

    - ``span.start_mono_ns`` and ``span.end_mono_ns`` are stamped on
      the span as attributes.
    - The duration is pushed onto the SPSC ring buffer.
    - Optionally records the duration into the
      ``quantbot_tick_to_trade_seconds`` histogram (default on).
    """
    start = time.monotonic_ns()
    with tracer.start_as_current_span(name, attributes=attributes or {}) as span:
        try:
            try:
                span.set_attribute("hft.start_mono_ns", start)
            except Exception:  # noqa: BLE001
                pass
            yield span
        finally:
            end = time.monotonic_ns()
            try:
                span.set_attribute("hft.end_mono_ns", end)
                span.set_attribute("hft.duration_ns", end - start)
            except Exception:  # noqa: BLE001
                pass
            try:
                _get_ring().push_nowait((name, start, end, attributes or {}))
            except Exception:  # noqa: BLE001
                pass
            if record_in_histogram:
                try:
                    from aqp_bots.telemetry.metrics import get_metrics

                    metrics = get_metrics()
                    venue = (attributes or {}).get("venue", "unknown")
                    variant = (attributes or {}).get("variant", "stable")
                    metrics.tick_to_trade_seconds.labels(  # type: ignore[union-attr]
                        variant=variant, venue=venue
                    ).observe((end - start) / 1e9)
                except Exception:  # noqa: BLE001
                    pass


__all__ = ["get_microsecond_ring", "hft_span"]
