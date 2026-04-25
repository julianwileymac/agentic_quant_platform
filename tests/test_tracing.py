"""OpenTelemetry tracing smoke tests.

Only run if the ``otel`` extra is installed; otherwise the decorator
still has to be callable (no-op tracer), which we verify explicitly.
"""
from __future__ import annotations

import pytest

from aqp.observability import traced
from aqp.observability.tracing import _otel_available


def test_traced_decorator_sync_noop_without_otel() -> None:
    """The decorator is always safe to apply, even without OTel installed."""

    @traced("unit.sync")
    def add(a: int, b: int) -> int:
        return a + b

    assert add(1, 2) == 3


@pytest.mark.asyncio
async def test_traced_decorator_async_noop() -> None:
    @traced("unit.async")
    async def add(a: int, b: int) -> int:
        return a + b

    assert await add(2, 3) == 5


@pytest.mark.skipif(not _otel_available(), reason="OTel SDK not installed")
def test_traced_emits_span_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the in-memory exporter installed, the decorator emits spans."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    @traced("unit.real", attributes={"unit": "yes"})
    def ping() -> str:
        return "pong"

    assert ping() == "pong"
    spans = exporter.get_finished_spans()
    assert any(s.name == "unit.real" for s in spans)
