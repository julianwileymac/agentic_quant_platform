"""Span decorators usable on sync and async functions alike.

Usage::

    from aqp.observability import traced

    @traced("paper.session.run")
    async def run(self) -> None:
        ...

    @traced("broker.submit_order", attributes={"venue": "alpaca"})
    def submit_order(self, request):
        ...
"""
from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

from aqp.observability.tracing import get_tracer


def traced(
    span_name: str,
    *,
    tracer_name: str = "aqp",
    attributes: dict[str, Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Wrap a callable in an OpenTelemetry span.

    Works transparently on sync and ``async`` functions. When OTEL is disabled
    the underlying tracer is a no-op, so overhead is a single attribute
    lookup per call.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        tracer = get_tracer(tracer_name)

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with tracer.start_as_current_span(span_name) as span:
                    for key, value in (attributes or {}).items():
                        span.set_attribute(key, value)
                    try:
                        return await fn(*args, **kwargs)
                    except Exception as exc:  # noqa: BLE001
                        span.record_exception(exc)
                        raise

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with tracer.start_as_current_span(span_name) as span:
                for key, value in (attributes or {}).items():
                    span.set_attribute(key, value)
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    span.record_exception(exc)
                    raise

        return sync_wrapper

    return decorator
