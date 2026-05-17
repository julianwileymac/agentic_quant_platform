from __future__ import annotations

from typing import Any

import pytest

from aqp.data.fabric.identity import FabricIdentity
from aqp.observability import fabric_bus


@pytest.fixture(autouse=True)
def _reset_bus_singleton() -> None:
    fabric_bus.ObservabilityBus._instance = None
    yield
    fabric_bus.ObservabilityBus._instance = None


def test_singleton_returns_same_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fabric_bus, "configure_tracing", lambda *_args, **_kwargs: None)
    first = fabric_bus.get_observability_bus()
    second = fabric_bus.get_observability_bus()
    assert first is second


def test_record_span_attaches_fabric_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )
    except ImportError:
        pytest.skip("opentelemetry-sdk is not installed")

    class _FakeFabric(FabricIdentity):
        def __init__(self, value: int) -> None:
            self.value = value

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("fabric-test")

    monkeypatch.setattr(fabric_bus, "configure_tracing", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(fabric_bus, "_get_tracer", lambda _name: tracer)

    bus = fabric_bus.get_observability_bus()
    fake = _FakeFabric(123)

    with bus.record_span("test.span", fabric_obj=fake):
        pass

    spans = exporter.get_finished_spans()
    assert spans
    attrs = spans[-1].attributes
    assert attrs["fabric.uuid"] == str(fake.fabric_uuid)
    assert attrs["fabric.content_hash"] == fake.content_hash


def test_instrument_loader_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fabric_bus, "configure_tracing", lambda *_args, **_kwargs: None)

    class _FakeLoader:
        PROVIDER_NAME = "fake"

        def fetch_batch(self) -> list[dict[str, int]]:
            return [{"value": 1}]

    decorated_once = fabric_bus.instrument_loader(_FakeLoader)
    method_ref: Any = decorated_once.fetch_batch
    decorated_twice = fabric_bus.instrument_loader(decorated_once)

    assert getattr(decorated_twice, "_fabric_loader_instrumented", False) is True
    assert decorated_twice.fetch_batch is method_ref


def test_metric_instruments_constructed_lazily(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fabric_bus, "configure_tracing", lambda *_args, **_kwargs: None)
    bus = fabric_bus.get_observability_bus()

    assert bus._instruments_initialized is False
    _counter = bus.records_fetched
    assert bus._instruments_initialized is True
