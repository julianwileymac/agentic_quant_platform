"""OpenTelemetry setup for the consumer template."""

from __future__ import annotations

import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


def configure_tracing(service_name: str, endpoint: str) -> trace.Tracer:
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "data-services",
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    logger.info("tracing -> %s as %s", endpoint, service_name)
    return trace.get_tracer(service_name)
