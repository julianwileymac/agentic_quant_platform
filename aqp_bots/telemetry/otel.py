"""Bot-scoped OpenTelemetry bootstrap.

Delegates to :func:`aqp.observability.tracing.configure_tracing` for
the heavy lifting (rpi_k8s_sdk integration, BatchSpanProcessor,
OTLP exporter selection) and adds bot-specific resource attributes
(``bot.id``, ``strategy.id``, ``run.id``, ``fleet.id``,
``service.namespace=quantbot``).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def configure_bot_tracing(
    *,
    bot_id: str,
    strategy_id: str | None = None,
    run_id: str | None = None,
    fleet_id: str | None = None,
    hft_mode: bool = False,
) -> Any:
    """Initialise OTEL for one bot pod.

    Returns the underlying tracer provider (or None when OTEL is
    disabled / not installed).

    When ``hft_mode=True`` and the optional dependencies are available,
    additionally installs :class:`HFTSpanProcessor` for sub-millisecond
    span emission (see :mod:`aqp_bots.telemetry.hft_processor`).
    """
    service_name = f"quantbot-bot-{bot_id}"
    try:
        from aqp.observability.tracing import configure_tracing

        provider = configure_tracing(service_name=service_name)
    except Exception:  # noqa: BLE001
        logger.exception("configure_bot_tracing: aqp.observability.tracing unavailable")
        provider = None

    if provider is not None:
        try:
            from opentelemetry.sdk.resources import Resource

            # Add bot-scoped resource attributes by re-creating the
            # resource and merging.
            attrs = {
                "bot.id": bot_id,
                "service.namespace": "quantbot",
            }
            if strategy_id:
                attrs["strategy.id"] = strategy_id
            if run_id:
                attrs["run.id"] = run_id
            if fleet_id:
                attrs["fleet.id"] = fleet_id
            # The SDK provider exposes `resource`; we merge non-destructively.
            existing = getattr(provider, "resource", Resource.create({}))
            merged = existing.merge(Resource.create(attrs))
            # Mutating the provider's resource isn't a public API but
            # it's the cleanest fix for late-binding attributes.
            provider._resource = merged  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            logger.debug("could not merge bot-scoped resource attributes", exc_info=True)

    if hft_mode and provider is not None:
        try:
            from aqp_bots.telemetry.hft_processor import HFTSpanProcessor

            provider.add_span_processor(HFTSpanProcessor())
            logger.info("HFTSpanProcessor attached for bot %s", bot_id)
        except Exception:  # noqa: BLE001
            logger.debug("could not attach HFTSpanProcessor", exc_info=True)

    return provider


def get_bot_tracer(name: str = "quantbot") -> Any:
    """Return a tracer (or a no-op fallback if OTEL is disabled)."""
    try:
        from aqp.observability.tracing import get_tracer

        return get_tracer(name)
    except Exception:  # noqa: BLE001
        return _NoopTracer()


class _NoopSpan:
    def set_attribute(self, *a: Any, **kw: Any) -> None: return
    def record_exception(self, *a: Any, **kw: Any) -> None: return
    def end(self) -> None: return
    def __enter__(self) -> _NoopSpan: return self
    def __exit__(self, *a: Any) -> None: return


class _NoopTracer:
    def start_as_current_span(self, *a: Any, **kw: Any) -> _NoopSpan: return _NoopSpan()
    def start_span(self, *a: Any, **kw: Any) -> _NoopSpan: return _NoopSpan()


__all__ = ["configure_bot_tracing", "get_bot_tracer"]
