"""OpenTelemetry bootstrap for AQP - delegates to ``rpi_k8s_sdk`` when present.

History
-------
AQP previously maintained its own copy of the OTel bootstrap logic.  That
created two divergent code paths with different env-var conventions
(``AQP_OTEL_*`` vs ``OTEL_*``), different sampling defaults, and different
instrumentor lists.  This module now delegates to the canonical helper in
``rpi_k8s_sdk.tracing`` whenever the SDK is installed - the SDK ships with
matching no-op fallbacks so the behavior degrades gracefully when the SDK
or the OpenTelemetry packages are missing.

The legacy ``AQP_OTEL_ENDPOINT`` / ``AQP_OTEL_PROTOCOL`` /
``AQP_OTEL_SAMPLE_RATIO`` env vars remain honored: the SDK's
``_default_otlp_endpoint`` /  ``_default_protocol`` /
``_default_sample_ratio`` helpers explicitly look them up as fallbacks.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)

_tracer_provider: Any = None
_instrumented: set[str] = set()


def _sdk_available() -> bool:
    """Return True iff the rpi_k8s_sdk tracing helper can be imported."""
    try:
        import rpi_k8s_sdk.tracing  # noqa: F401

        return True
    except ImportError:
        return False


def _otel_available() -> bool:
    """Return True iff the OpenTelemetry SDK can be imported."""
    try:
        import opentelemetry  # noqa: F401
        import opentelemetry.sdk  # noqa: F401

        return True
    except ImportError:
        return False


def configure_tracing(service_name: str | None = None) -> Any:
    """Initialise the global TracerProvider via the canonical SDK helper.

    Idempotent and safe to call repeatedly.  Returns the ``TracerProvider``
    or ``None`` when both the SDK and the OTel SDK are missing/disabled.
    """
    global _tracer_provider

    if _tracer_provider is not None:
        return _tracer_provider
    if not settings.otel_enabled:
        logger.debug("OTEL disabled (AQP_OTEL_ENDPOINT empty); skipping tracer setup")
        return None

    name = service_name or settings.otel_service_name

    if _sdk_available():
        from rpi_k8s_sdk.tracing import configure_tracing as _sdk_configure

        provider = _sdk_configure(
            service_name=name,
            endpoint=settings.otel_endpoint,
            protocol=settings.otel_protocol,
            namespace="aqp",
            sample_ratio=settings.otel_sample_ratio,
            instrument_kafka=False,
            instrument_httpx=True,
        )
        _tracer_provider = provider
        return provider

    if not _otel_available():
        logger.warning(
            "AQP_OTEL_ENDPOINT is set but neither rpi_k8s_sdk nor opentelemetry-sdk "
            'is installed; install with `pip install -e ".[otel]"`'
        )
        return None

    # Last-resort fallback: the SDK is missing but raw OTel packages are
    # available.  Replicate a minimal subset of the SDK's behaviour so AQP
    # can still trace in environments where rpi-k8s-sdk has not been pinned.
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    resource = Resource.create(
        {
            "service.name": name,
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
        "OTEL tracing initialised (no SDK): service=%s endpoint=%s sample_ratio=%.2f",
        name,
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
    if _sdk_available():
        from rpi_k8s_sdk.tracing import get_tracer as _sdk_get_tracer

        return _sdk_get_tracer(name)
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
    if _sdk_available():
        from rpi_k8s_sdk.tracing import shutdown_tracing as _sdk_shutdown

        _sdk_shutdown()
        _tracer_provider = None
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
