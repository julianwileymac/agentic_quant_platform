"""OpenTelemetry setup - delegates to the canonical ``rpi_k8s_sdk`` helper.

The management backend used to maintain its own copy of the OTel bootstrap
logic.  It now defers to :func:`rpi_k8s_sdk.tracing.configure_tracing` so the
backend, the SDK, the pipelines workers, and the Agentic Quant Platform all
behave identically (same endpoint resolution, same sampler, same instrumentor
list).
"""

import logging

from ..config import Settings

logger = logging.getLogger(__name__)


def setup_telemetry(settings: Settings, app=None) -> None:
    """Configure OpenTelemetry tracing via the SDK helper.

    Parameters
    ----------
    settings:
        Loaded :class:`Settings` instance (drives endpoint + service name).
    app:
        Optional FastAPI application.  When provided, the FastAPI instrumentor
        is attached so request spans show up automatically.
    """

    if not settings.telemetry.enabled:
        logger.info("OpenTelemetry disabled")
        return

    try:
        from rpi_k8s_sdk.tracing import configure_tracing
    except ImportError:
        logger.warning(
            "rpi_k8s_sdk not installed; falling back to no-op telemetry. "
            "Install the SDK with `pip install -e ../sdk` to enable tracing."
        )
        return

    configure_tracing(
        service_name=settings.telemetry.service_name,
        endpoint=settings.telemetry.exporter_endpoint,
        namespace="management",
        instrument_kafka=False,
        instrument_httpx=True,
        instrument_fastapi_app=app,
        instrument_redis_clients=True,
    )
    logger.info(
        "OpenTelemetry configured via SDK: exporting to %s",
        settings.telemetry.exporter_endpoint,
    )
