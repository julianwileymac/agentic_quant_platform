"""OpenTelemetry bootstrap — wires an OTLP exporter and auto-instrumentation.

All imports are lazy so the base install stays lean. When the ``otel`` extra
is missing every function short-circuits to a no-op, which keeps
``from aqp.observability import traced`` safe everywhere.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)

_tracer_provider: Any = None
_instrumented: set[str] = set()


def _otel_available() -> bool:
    try:
        import opentelemetry  # noqa: F401
        import opentelemetry.sdk  # noqa: F401

        return True
    except ImportError:
        return False


def configure_tracing(service_name: str | None = None) -> Any:
    """Initialise the global TracerProvider and OTLP exporter.

    Idempotent and safe to call repeatedly. Returns the ``TracerProvider`` or
    ``None`` when the OTel SDK is missing / disabled.
    """
    global _tracer_provider

    if _tracer_provider is not None:
        return _tracer_provider
    if not settings.otel_enabled:
        logger.debug("OTEL disabled (AQP_OTEL_ENDPOINT empty); skipping tracer setup")
        return None
    if not _otel_available():
        logger.warning(
            "AQP_OTEL_ENDPOINT is set but opentelemetry-sdk is not installed; "
            'install with `pip install -e ".[otel]"`'
        )
        return None

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    resource = Resource.create(
        {
            "service.name": service_name or settings.otel_service_name,
            "service.namespace": "aqp",
            "deployment.environment": settings.env,
        }
    )
    sampler = ParentBased(TraceIdRatioBased(settings.otel_sample_ratio))
    provider = TracerProvider(resource=resource, sampler=sampler)

    exporter = _build_exporter()
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _tracer_provider = provider
    logger.info(
        "OTEL tracing initialised: service=%s endpoint=%s sample_ratio=%.2f",
        service_name or settings.otel_service_name,
        settings.otel_endpoint,
        settings.otel_sample_ratio,
    )
    return provider


def _build_exporter() -> Any:
    try:
        if settings.otel_protocol == "http/protobuf":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            return OTLPSpanExporter(endpoint=settings.otel_endpoint)
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        return OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
    except ImportError:
        logger.warning("OTLP exporter not installed; spans will not be exported")
        return None


def get_tracer(name: str = "aqp") -> Any:
    """Return an OpenTelemetry tracer, or a silent no-op if disabled."""
    if not _otel_available():
        return _NoopTracer()
    from opentelemetry import trace

    return trace.get_tracer(name)


def instrument_fastapi(app: Any) -> None:
    """Attach ``FastAPIInstrumentor`` to an app. Safe if already instrumented."""
    if "fastapi" in _instrumented or not settings.otel_enabled or not _otel_available():
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        _instrumented.add("fastapi")
        logger.info("FastAPI OTEL instrumentation attached")
    except ImportError:
        logger.warning("opentelemetry-instrumentation-fastapi missing")


def instrument_celery() -> None:
    """Instrument Celery signals. Safe if already instrumented."""
    if "celery" in _instrumented or not settings.otel_enabled or not _otel_available():
        return
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().instrument()
        _instrumented.add("celery")
        logger.info("Celery OTEL instrumentation attached")
    except ImportError:
        logger.warning("opentelemetry-instrumentation-celery missing")


def instrument_sqlalchemy(engine: Any) -> None:
    """Instrument an SQLAlchemy engine."""
    if "sqlalchemy" in _instrumented or not settings.otel_enabled or not _otel_available():
        return
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine)
        _instrumented.add("sqlalchemy")
    except ImportError:
        logger.warning("opentelemetry-instrumentation-sqlalchemy missing")


def instrument_httpx() -> None:
    if "httpx" in _instrumented or not settings.otel_enabled or not _otel_available():
        return
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        _instrumented.add("httpx")
    except ImportError:
        logger.warning("opentelemetry-instrumentation-httpx missing")


def instrument_redis() -> None:
    if "redis" in _instrumented or not settings.otel_enabled or not _otel_available():
        return
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
        _instrumented.add("redis")
    except ImportError:
        logger.warning("opentelemetry-instrumentation-redis missing")


def shutdown_tracing() -> None:
    """Flush + shutdown the global provider (called on service exit)."""
    global _tracer_provider
    if _tracer_provider is None:
        return
    try:
        _tracer_provider.shutdown()
    except Exception:
        logger.exception("error shutting down tracer provider")
    finally:
        _tracer_provider = None


# ---------------------------------------------------------------------------
# No-op fallbacks so callers never need to guard against missing OTEL.
# ---------------------------------------------------------------------------


class _NoopSpan:
    def set_attribute(self, *_args: Any, **_kwargs: Any) -> None:
        return

    def record_exception(self, *_args: Any, **_kwargs: Any) -> None:
        return

    def set_status(self, *_args: Any, **_kwargs: Any) -> None:
        return

    def end(self) -> None:
        return

    def __enter__(self) -> _NoopSpan:
        return self

    def __exit__(self, *_args: Any) -> None:
        return


class _NoopTracer:
    def start_as_current_span(self, *_args: Any, **_kwargs: Any) -> _NoopSpan:
        return _NoopSpan()

    def start_span(self, *_args: Any, **_kwargs: Any) -> _NoopSpan:
        return _NoopSpan()
