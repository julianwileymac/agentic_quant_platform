from __future__ import annotations

import inspect
import json
import logging
import threading
from collections.abc import AsyncIterator, Iterable, Iterator, Mapping
from contextlib import contextmanager
from functools import wraps
from typing import Any

from aqp.config import settings
from aqp.data.fabric.identity import FabricIdentity, VersionVector
from aqp.data.fabric.schema_registry import SchemaValidationError
from aqp.observability import configure_tracing, get_tracer as _get_tracer

logger = logging.getLogger(__name__)


class _NoopInstrument:
    def add(self, *_args: Any, **_kwargs: Any) -> None:
        return

    def record(self, *_args: Any, **_kwargs: Any) -> None:
        return


class _NoopMeter:
    def create_counter(self, *_args: Any, **_kwargs: Any) -> _NoopInstrument:
        return _NoopInstrument()

    def create_histogram(self, *_args: Any, **_kwargs: Any) -> _NoopInstrument:
        return _NoopInstrument()


def _as_span_attribute(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _row_count(value: Any) -> int:
    if value is None:
        return 0
    if hasattr(value, "num_rows"):
        try:
            return int(value.num_rows)
        except (TypeError, ValueError):
            return 0
    try:
        return int(len(value))
    except (TypeError, ValueError):
        return 1


def _is_batch_iterable(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (str, bytes, bytearray, dict)):
        return False
    if hasattr(value, "num_rows"):
        return False
    return isinstance(value, Iterable)


def _infer_persisted_rows(result: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> int:
    if isinstance(result, int):
        return max(0, result)
    if result is not None and hasattr(result, "num_rows"):
        return max(0, _row_count(result))
    table = kwargs.get("table")
    if table is None and args:
        table = args[0]
    if table is not None and hasattr(table, "num_rows"):
        return max(0, _row_count(table))
    return 0


class ObservabilityBus:
    _instance: ObservabilityBus | None = None
    _instance_lock = threading.Lock()
    _warned_missing_otel = False

    def __new__(cls) -> ObservabilityBus:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return

        configure_tracing(service_name=settings.otel_service_name)
        self._instrument_lock = threading.Lock()
        self._instruments_initialized = False
        self._meter: Any | None = None
        self._records_fetched: Any | None = None
        self._records_persisted: Any | None = None
        self._batch_duration: Any | None = None
        self._schema_errors: Any | None = None
        self._hash_collisions: Any | None = None
        self._initialized = True

    @classmethod
    def _warn_missing_otel_once(cls) -> None:
        if cls._warned_missing_otel:
            return
        cls._warned_missing_otel = True
        logger.warning(
            "OpenTelemetry SDK not available; ObservabilityBus metrics are no-op stubs"
        )

    def get_tracer(self, name: str) -> Any:
        return _get_tracer(name)

    def get_meter(self, name: str) -> Any:
        try:
            from opentelemetry import metrics
            import opentelemetry.sdk.metrics  # noqa: F401
        except ImportError:
            self._warn_missing_otel_once()
            return _NoopMeter()
        return metrics.get_meter(name)

    def _ensure_instruments(self) -> None:
        if self._instruments_initialized:
            return
        with self._instrument_lock:
            if self._instruments_initialized:
                return
            meter = self.get_meter("aqp.fabric")
            self._meter = meter
            self._records_fetched = meter.create_counter(
                "aqp.ingestion.records_fetched",
                unit="{records}",
                description="Records fetched by loader operations",
            )
            self._records_persisted = meter.create_counter(
                "aqp.ingestion.records_persisted",
                unit="{records}",
                description="Records persisted by loader operations",
            )
            self._batch_duration = meter.create_histogram(
                "aqp.ingestion.batch_duration",
                unit="ms",
                description="Batch duration in milliseconds",
            )
            self._schema_errors = meter.create_counter(
                "aqp.ingestion.schema_errors",
                unit="{errors}",
                description="Schema validation errors",
            )
            self._hash_collisions = meter.create_counter(
                "aqp.loader.hash_collisions",
                unit="{events}",
                description="Content hash collision events",
            )
            self._instruments_initialized = True

    @property
    def records_fetched(self) -> Any:
        self._ensure_instruments()
        return self._records_fetched or _NoopInstrument()

    @property
    def records_persisted(self) -> Any:
        self._ensure_instruments()
        return self._records_persisted or _NoopInstrument()

    @property
    def batch_duration(self) -> Any:
        self._ensure_instruments()
        return self._batch_duration or _NoopInstrument()

    @property
    def schema_errors(self) -> Any:
        self._ensure_instruments()
        return self._schema_errors or _NoopInstrument()

    @property
    def hash_collisions(self) -> Any:
        self._ensure_instruments()
        return self._hash_collisions or _NoopInstrument()

    @contextmanager
    def record_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, Any] | None = None,
        fabric_obj: FabricIdentity | None = None,
    ) -> Iterator[Any]:
        tracer = self.get_tracer("aqp.fabric")
        with tracer.start_as_current_span(name) as span:
            try:
                if fabric_obj is not None:
                    span.set_attribute("fabric.uuid", str(fabric_obj.fabric_uuid))
                    span.set_attribute("fabric.content_hash", str(fabric_obj.content_hash))
                    version_vector = fabric_obj.version_vector
                    compact_vector = (
                        version_vector.to_dict()
                        if isinstance(version_vector, VersionVector)
                        else version_vector
                    )
                    span.set_attribute(
                        "fabric.version_vector",
                        json.dumps(
                            compact_vector,
                            sort_keys=True,
                            separators=(",", ":"),
                            default=str,
                        ),
                    )
                for key, value in (attributes or {}).items():
                    span.set_attribute(key, _as_span_attribute(value))
                yield span
            except Exception as exc:
                span.record_exception(exc)
                try:
                    from opentelemetry.trace import Status, StatusCode
                except ImportError:
                    pass
                else:
                    span.set_status(Status(StatusCode.ERROR))
                raise


def get_observability_bus() -> ObservabilityBus:
    return ObservabilityBus()


def record_span(
    name: str,
    *,
    attributes: Mapping[str, Any] | None = None,
    fabric_obj: FabricIdentity | None = None,
) -> Iterator[Any]:
    return get_observability_bus().record_span(
        name,
        attributes=attributes,
        fabric_obj=fabric_obj,
    )


def _wrap_sync_fetch(
    *,
    bus: ObservabilityBus,
    fn: Any,
    span_name: str,
) -> Any:
    if inspect.isgeneratorfunction(fn):

        @wraps(fn)
        def wrapped(self: Any, *args: Any, **kwargs: Any) -> Iterator[Any]:
            with bus.record_span(span_name):
                for batch in fn(self, *args, **kwargs):
                    bus.records_fetched.add(_row_count(batch))
                    yield batch

        return wrapped

    @wraps(fn)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = fn(self, *args, **kwargs)
        if isinstance(result, Iterator):

            def counted_iterator() -> Iterator[Any]:
                with bus.record_span(span_name):
                    for batch in result:
                        bus.records_fetched.add(_row_count(batch))
                        yield batch

            return counted_iterator()

        with bus.record_span(span_name):
            if _is_batch_iterable(result):
                total = 0
                for batch in result:
                    total += _row_count(batch)
                bus.records_fetched.add(total)
            else:
                bus.records_fetched.add(_row_count(result))
            return result

    return wrapped


def _wrap_async_fetch(
    *,
    bus: ObservabilityBus,
    fn: Any,
    span_name: str,
) -> Any:
    if inspect.isasyncgenfunction(fn):

        @wraps(fn)
        async def wrapped(self: Any, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
            with bus.record_span(span_name):
                async for batch in fn(self, *args, **kwargs):
                    bus.records_fetched.add(_row_count(batch))
                    yield batch

        return wrapped

    @wraps(fn)
    async def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        with bus.record_span(span_name):
            result = await fn(self, *args, **kwargs)
            bus.records_fetched.add(_row_count(result))
            return result

    return wrapped


def _wrap_schema_method(*, bus: ObservabilityBus, fn: Any, span_name: str) -> Any:
    if inspect.iscoroutinefunction(fn):

        @wraps(fn)
        async def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                with bus.record_span(span_name):
                    return await fn(self, *args, **kwargs)
            except SchemaValidationError:
                bus.schema_errors.add(1)
                raise

        return wrapped

    @wraps(fn)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            with bus.record_span(span_name):
                return fn(self, *args, **kwargs)
        except SchemaValidationError:
            bus.schema_errors.add(1)
            raise

    return wrapped


def _wrap_persist_method(*, bus: ObservabilityBus, fn: Any, span_name: str) -> Any:
    if inspect.iscoroutinefunction(fn):

        @wraps(fn)
        async def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            with bus.record_span(span_name):
                result = await fn(self, *args, **kwargs)
                bus.records_persisted.add(_infer_persisted_rows(result, args, kwargs))
                return result

        return wrapped

    @wraps(fn)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        with bus.record_span(span_name):
            result = fn(self, *args, **kwargs)
            bus.records_persisted.add(_infer_persisted_rows(result, args, kwargs))
            return result

    return wrapped


def instrument_loader(cls: type) -> type:
    if getattr(cls, "_fabric_loader_instrumented", False):
        return cls

    bus = get_observability_bus()
    provider_name = getattr(cls, "PROVIDER_NAME", None) or cls.__name__
    fetch_method_name: str | None = None
    for candidate in ("fetch_batch", "fetch", "afetch"):
        if hasattr(cls, candidate):
            fetch_method_name = candidate
            break

    if fetch_method_name is not None:
        fetch_fn = getattr(cls, fetch_method_name)
        span_name = f"loader.{provider_name}.fetch"
        if inspect.iscoroutinefunction(fetch_fn) or inspect.isasyncgenfunction(fetch_fn):
            wrapped_fetch = _wrap_async_fetch(bus=bus, fn=fetch_fn, span_name=span_name)
        else:
            wrapped_fetch = _wrap_sync_fetch(bus=bus, fn=fetch_fn, span_name=span_name)
        setattr(cls, fetch_method_name, wrapped_fetch)

    if hasattr(cls, "normalize_schema"):
        normalize_fn = getattr(cls, "normalize_schema")
        setattr(
            cls,
            "normalize_schema",
            _wrap_schema_method(
                bus=bus,
                fn=normalize_fn,
                span_name=f"loader.{provider_name}.normalize_schema",
            ),
        )

    if hasattr(cls, "persist_to_iceberg"):
        persist_fn = getattr(cls, "persist_to_iceberg")
        setattr(
            cls,
            "persist_to_iceberg",
            _wrap_persist_method(
                bus=bus,
                fn=persist_fn,
                span_name=f"loader.{provider_name}.persist_to_iceberg",
            ),
        )

    setattr(cls, "_fabric_loader_instrumented", True)
    return cls


__all__ = [
    "ObservabilityBus",
    "get_observability_bus",
    "instrument_loader",
    "record_span",
]
