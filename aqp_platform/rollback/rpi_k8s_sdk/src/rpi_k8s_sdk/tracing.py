"""Canonical OpenTelemetry helper for the rpi_kubernetes platform.

This module is the single point of entry for tracing across:

* the management backend (FastAPI)
* the pipelines workers (Celery + Dagster)
* every Python service that ``pip install``s ``rpi-k8s-sdk``
* the Agentic Quant Platform (delegates here when the SDK is installed)

Design goals
------------
1. **Idempotent** - safe to call ``configure_tracing(...)`` more than once.
2. **Soft-optional** - if the OpenTelemetry SDK is not installed, every
   function returns / instruments a silent no-op.  Callers never need to
   guard the import.
3. **Cluster-aware defaults** - chooses the in-cluster collector DNS when
   running inside Kubernetes; falls back to a local 127.0.0.1 tunnel when
   running on a developer laptop.
4. **Protocol switch** - supports OTLP/gRPC (4317) and OTLP/HTTP (4318) so
   downstream networking constraints (e.g. service-mesh mTLS, ingress
   limitations) can be worked around without code changes.
5. **Sampler** - ParentBased + TraceIdRatio so child spans inherit the
   parent decision but cluster-wide volume stays bounded.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_tracer_provider: Any = None
_instrumented: set[str] = set()


def _otel_available() -> bool:
    """Return True iff the OpenTelemetry SDK can be imported."""

    try:
        import opentelemetry  # noqa: F401
        import opentelemetry.sdk  # noqa: F401

        return True
    except ImportError:
        return False


def _default_otlp_endpoint() -> str:
    """Pick the best OTLP endpoint for the current execution context.

    Priority:
        1. Explicit ``OTEL_EXPORTER_OTLP_ENDPOINT`` env var.
        2. Legacy ``AQP_OTEL_ENDPOINT`` env var (kept for AQP back-compat).
        3. In-cluster DNS (``otel-collector.observability.svc.cluster.local``)
           when ``KUBERNETES_SERVICE_HOST`` is set.
        4. Loopback for ``kubectl port-forward`` based dev loops.
    """

    if endpoint := os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return endpoint
    if endpoint := os.environ.get("AQP_OTEL_ENDPOINT"):
        return endpoint
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        return "http://otel-collector.observability.svc.cluster.local:4317"
    return "http://127.0.0.1:4317"


def _default_protocol() -> str:
    """Return ``grpc`` or ``http/protobuf`` based on env vars."""

    proto = (
        os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL")
        or os.environ.get("AQP_OTEL_PROTOCOL")
        or "grpc"
    ).lower()
    if proto in ("http", "http/protobuf"):
        return "http/protobuf"
    return "grpc"


def _default_sample_ratio() -> float:
    """Read ``OTEL_TRACES_SAMPLER_ARG`` (or AQP equivalent), default 1.0."""

    raw = (
        os.environ.get("OTEL_TRACES_SAMPLER_ARG")
        or os.environ.get("AQP_OTEL_SAMPLE_RATIO")
        or "1.0"
    )
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return 1.0


def configure_tracing(
    service_name: str,
    *,
    endpoint: Optional[str] = None,
    protocol: Optional[str] = None,
    namespace: str = "data-services",
    sample_ratio: Optional[float] = None,
    instrument_kafka: bool = True,
    instrument_httpx: bool = True,
    instrument_fastapi_app: Any = None,
    instrument_celery_signals: bool = False,
    instrument_redis_clients: bool = False,
    instrument_sqlalchemy_engine: Any = None,
) -> Any:
    """Install an OTLP tracer provider and (optionally) auto-instrument SDKs.

    Parameters
    ----------
    service_name:
        Logical service name reported on every span (``service.name`` resource
        attribute).
    endpoint:
        OTLP endpoint URL.  When ``None``, :func:`_default_otlp_endpoint` picks
        the best in-cluster / local-dev URL.
    protocol:
        ``"grpc"`` or ``"http/protobuf"``.  ``None`` -> :func:`_default_protocol`.
    namespace:
        Logical service namespace (``service.namespace`` resource attribute).
    sample_ratio:
        Float in ``[0.0, 1.0]``.  Wraps :class:`TraceIdRatioBased` in a
        :class:`ParentBased` sampler so child spans honour parent decisions.
    instrument_kafka:
        Auto-instrument confluent-kafka and aiokafka when they are installed.
    instrument_httpx:
        Auto-instrument the ``httpx`` client.
    instrument_fastapi_app:
        Pass a ``FastAPI`` instance to attach the FastAPI instrumentor.
    instrument_celery_signals:
        Attach the Celery signal-based instrumentor (no-op on import error).
    instrument_redis_clients:
        Globally instrument the ``redis`` client (sync + asyncio).
    instrument_sqlalchemy_engine:
        Pass a SQLAlchemy ``Engine`` instance to attach the SQLAlchemy
        instrumentor for that engine.

    Returns
    -------
    The configured ``TracerProvider`` (or ``None`` when OTel is unavailable).
    """

    global _tracer_provider

    if _tracer_provider is not None:
        # Idempotent - still attach late-bound instrumentors though.
        _attach_optional_instrumentors(
            instrument_kafka=instrument_kafka,
            instrument_httpx=instrument_httpx,
            instrument_fastapi_app=instrument_fastapi_app,
            instrument_celery_signals=instrument_celery_signals,
            instrument_redis_clients=instrument_redis_clients,
            instrument_sqlalchemy_engine=instrument_sqlalchemy_engine,
        )
        return _tracer_provider

    if not _otel_available():
        logger.warning("opentelemetry packages missing; tracing disabled.")
        return None

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    endpoint = endpoint or _default_otlp_endpoint()
    protocol = protocol or _default_protocol()
    sample_ratio = sample_ratio if sample_ratio is not None else _default_sample_ratio()

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": namespace,
            "deployment.environment": os.environ.get("OTEL_ENV", "rpi-cluster"),
            "cluster.name": os.environ.get("CLUSTER_NAME", "rpi-k8s-cluster"),
        }
    )

    sampler = ParentBased(TraceIdRatioBased(sample_ratio))
    provider = TracerProvider(resource=resource, sampler=sampler)

    exporter = _build_exporter(endpoint, protocol)
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _tracer_provider = provider

    _attach_optional_instrumentors(
        instrument_kafka=instrument_kafka,
        instrument_httpx=instrument_httpx,
        instrument_fastapi_app=instrument_fastapi_app,
        instrument_celery_signals=instrument_celery_signals,
        instrument_redis_clients=instrument_redis_clients,
        instrument_sqlalchemy_engine=instrument_sqlalchemy_engine,
    )

    logger.info(
        "tracing configured service=%s endpoint=%s protocol=%s sample=%.2f",
        service_name,
        endpoint,
        protocol,
        sample_ratio,
    )
    return provider


def _build_exporter(endpoint: str, protocol: str) -> Any:
    """Construct the matching OTLP span exporter for the requested protocol."""

    try:
        if protocol == "http/protobuf":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            return OTLPSpanExporter(endpoint=endpoint)
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        return OTLPSpanExporter(endpoint=endpoint, insecure=True)
    except ImportError:
        logger.warning("OTLP exporter not installed; spans will not be exported")
        return None


def _attach_optional_instrumentors(
    *,
    instrument_kafka: bool,
    instrument_httpx: bool,
    instrument_fastapi_app: Any,
    instrument_celery_signals: bool,
    instrument_redis_clients: bool,
    instrument_sqlalchemy_engine: Any,
) -> None:
    """Attach every requested auto-instrumentor; missing packages are silent."""

    if instrument_kafka and "kafka" not in _instrumented:
        try:
            from opentelemetry.instrumentation.confluent_kafka import (
                ConfluentKafkaInstrumentor,
            )

            ConfluentKafkaInstrumentor().instrument()
            _instrumented.add("kafka")
        except ImportError:
            logger.debug("opentelemetry-instrumentation-confluent-kafka not installed")
        try:
            from opentelemetry.instrumentation.aiokafka import AIOKafkaInstrumentor

            AIOKafkaInstrumentor().instrument()
            _instrumented.add("aiokafka")
        except ImportError:
            logger.debug("opentelemetry-instrumentation-aiokafka not installed")

    if instrument_httpx and "httpx" not in _instrumented:
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

            HTTPXClientInstrumentor().instrument()
            _instrumented.add("httpx")
        except ImportError:
            logger.debug("opentelemetry-instrumentation-httpx not installed")

    if instrument_fastapi_app is not None and "fastapi" not in _instrumented:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(instrument_fastapi_app)
            _instrumented.add("fastapi")
        except ImportError:
            logger.debug("opentelemetry-instrumentation-fastapi not installed")

    if instrument_celery_signals and "celery" not in _instrumented:
        try:
            from opentelemetry.instrumentation.celery import CeleryInstrumentor

            CeleryInstrumentor().instrument()
            _instrumented.add("celery")
        except ImportError:
            logger.debug("opentelemetry-instrumentation-celery not installed")

    if instrument_redis_clients and "redis" not in _instrumented:
        try:
            from opentelemetry.instrumentation.redis import RedisInstrumentor

            RedisInstrumentor().instrument()
            _instrumented.add("redis")
        except ImportError:
            logger.debug("opentelemetry-instrumentation-redis not installed")

    if instrument_sqlalchemy_engine is not None and "sqlalchemy" not in _instrumented:
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

            SQLAlchemyInstrumentor().instrument(engine=instrument_sqlalchemy_engine)
            _instrumented.add("sqlalchemy")
        except ImportError:
            logger.debug("opentelemetry-instrumentation-sqlalchemy not installed")


def get_tracer(name: str = "rpi_k8s_sdk") -> Any:
    """Return an OpenTelemetry tracer (or a silent no-op when disabled)."""

    if not _otel_available():
        return _NoopTracer()
    from opentelemetry import trace

    return trace.get_tracer(name)


def shutdown_tracing() -> None:
    """Flush + shutdown the global provider (call on service exit)."""

    global _tracer_provider
    if _tracer_provider is None:
        return
    try:
        _tracer_provider.shutdown()
    except Exception:
        logger.exception("error shutting down tracer provider")
    finally:
        _tracer_provider = None
        _instrumented.clear()


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

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, *_args: Any) -> None:
        return


class _NoopTracer:
    def start_as_current_span(self, *_args: Any, **_kwargs: Any) -> _NoopSpan:
        return _NoopSpan()

    def start_span(self, *_args: Any, **_kwargs: Any) -> _NoopSpan:
        return _NoopSpan()
