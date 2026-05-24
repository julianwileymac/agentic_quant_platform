"""Arize Phoenix bootstrap for AQP LLM / agent / RAG observability.

Phase 2d of the AQP infra-expansion plan. Phoenix is self-hosted in
the ``aqp-observability`` namespace; this module is the AQP-side
instrumentation entry point.

Phoenix sits NEXT TO the existing OTel pipeline:

- Existing :func:`aqp.observability.tracing.configure_tracing` keeps
  emitting infra spans (FastAPI / Celery / SQLAlchemy / httpx /
  Redis / Kafka) to the OTel Collector gateway.
- :func:`aqp.observability.phoenix.configure_phoenix` adds the
  OpenInference auto-instrumentations on top so LLM / agent / RAG
  call paths (OpenAI, LiteLLM, Anthropic, LangChain, LlamaIndex,
  CrewAI, DSPy) emit spans with ``openinference.span.kind`` set.
- The OTel gateway routes those AI-tagged spans to Phoenix, the rest
  to Tempo (see ``aqp_platform/deployments/kubernetes/observability/opentelemetry-collector-gateway/collector-gateway.yaml``).

Idempotent and safe to call repeatedly. Soft-fails when the
``arize-phoenix-otel`` package is missing (Phoenix observability is
optional; absent installs degrade to "OTel infra spans only").
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)


_phoenix_provider: Any = None
_phoenix_instrumented: set[str] = set()


def _phoenix_endpoint() -> str:
    """Resolve the Phoenix OTLP endpoint from settings.

    Resolution order:
    1. ``settings.phoenix_endpoint`` (HTTP OTLP, default to port 6006).
    2. ``settings.phoenix_grpc_endpoint`` (gRPC OTLP, port 4317).
    3. Empty -> bootstrap is a no-op (returned as None).
    """
    return (
        getattr(settings, "phoenix_endpoint", "")
        or getattr(settings, "phoenix_grpc_endpoint", "")
        or ""
    )


def configure_phoenix(
    *,
    project_name: str | None = None,
    auto_instrument: bool = True,
    batch: bool = True,
) -> Any:
    """Initialise the Phoenix tracer provider.

    Returns the Phoenix-managed ``TracerProvider`` or ``None`` when
    the package is missing or the endpoint is unset. Idempotent.
    """
    global _phoenix_provider

    if _phoenix_provider is not None:
        return _phoenix_provider

    endpoint = _phoenix_endpoint()
    if not endpoint:
        logger.debug(
            "Phoenix bootstrap skipped: settings.phoenix_endpoint and "
            "settings.phoenix_grpc_endpoint both unset"
        )
        return None

    try:
        from phoenix.otel import register
    except ImportError:
        logger.info(
            "arize-phoenix-otel not installed; Phoenix AI observability skipped"
        )
        return None

    project = (
        project_name
        or getattr(settings, "phoenix_project_default", "")
        or "aqp"
    )
    protocol = "grpc" if endpoint.startswith(("grpc://", "tcp://")) or ":4317" in endpoint else "http/protobuf"

    try:
        provider = register(
            project_name=project,
            endpoint=endpoint,
            protocol=protocol,
            auto_instrument=auto_instrument,
            batch=batch,
        )
    except Exception:  # noqa: BLE001
        logger.warning("phoenix.otel.register() raised", exc_info=True)
        return None

    _phoenix_provider = provider
    logger.info(
        "Phoenix tracing initialised: project=%s endpoint=%s protocol=%s "
        "auto_instrument=%s",
        project,
        endpoint,
        protocol,
        auto_instrument,
    )
    return provider


def configure_phoenix_for_app() -> Any:
    """Wrapper invoked from ``aqp/api/main.py`` after ``configure_tracing()``.

    Keeps the call site terse and lets us add API-specific instrumentations
    (e.g. a FastAPI middleware for span tagging) without touching every
    caller.
    """
    return configure_phoenix(project_name="aqp-api")


def configure_phoenix_for_celery() -> Any:
    """Wrapper for ``aqp/tasks/celery_app.py``.

    Celery workers run agentic flows (the bulk of the LLM traffic) so
    Phoenix runs in worker processes too. The bootstrap is per-process
    and idempotent.
    """
    return configure_phoenix(project_name="aqp-worker")


def using_session_id(session_id: str | None) -> Any:
    """Return the Phoenix ``using_session`` context manager if available.

    Use::

        with using_session_id(request_id):
            response = router_complete(...)

    so the AI / LLM spans emitted inside the block are tagged with the
    session ID in the Phoenix UI. When the package is missing, returns
    a no-op context manager so call sites keep working.
    """
    try:
        from phoenix.otel import using_session  # type: ignore[import]
    except ImportError:
        return _NoopContext()
    if not session_id:
        return _NoopContext()
    return using_session(session_id=session_id)


def using_attributes(**kwargs: Any) -> Any:
    """Return the Phoenix ``using_attributes`` context manager."""
    try:
        from phoenix.otel import using_attributes as _uattrs  # type: ignore[import]
    except ImportError:
        return _NoopContext()
    if not kwargs:
        return _NoopContext()
    return _uattrs(**kwargs)


def shutdown_phoenix() -> None:
    """Drop the cached Phoenix provider on process exit."""
    global _phoenix_provider
    if _phoenix_provider is None:
        return
    try:
        shutdown = getattr(_phoenix_provider, "shutdown", None)
        if callable(shutdown):
            shutdown()
    except Exception:  # noqa: BLE001
        logger.warning("Phoenix tracer provider shutdown raised", exc_info=True)
    finally:
        _phoenix_provider = None
        _phoenix_instrumented.clear()


class _NoopContext:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: Any) -> None:
        return None


__all__ = [
    "configure_phoenix",
    "configure_phoenix_for_app",
    "configure_phoenix_for_celery",
    "shutdown_phoenix",
    "using_attributes",
    "using_session_id",
]
