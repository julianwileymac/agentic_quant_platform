"""OpenTelemetry setup shared by all producers built from this template."""

from __future__ import annotations

import logging
from typing import Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


def configure_tracing(service_name: str, otlp_endpoint: str) -> trace.Tracer:
    """Install an OTLP/gRPC tracer provider and return a tracer."""

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "data-services",
            "deployment.environment": "rpi-cluster",
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    logger.info("OTel tracing exporting to %s as %s", otlp_endpoint, service_name)
    return trace.get_tracer(service_name)


def instrument_kafka_confluent(tracer: Optional[trace.Tracer] = None) -> None:
    """Attach the confluent-kafka auto-instrumentation.

    The decorator adds producer.send + consumer.poll spans automatically and
    propagates W3C Trace Context headers.
    """

    try:
        from opentelemetry.instrumentation.confluent_kafka import (
            ConfluentKafkaInstrumentor,
        )
    except ImportError:
        logger.warning(
            "opentelemetry-instrumentation-confluent-kafka not installed; "
            "producer spans will not be emitted."
        )
        return
    ConfluentKafkaInstrumentor().instrument()
