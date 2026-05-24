"""Tracing utilities and decorators."""

import asyncio
import functools
from typing import Any, Callable, Optional

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

# Global tracer instance
_tracer: Optional[trace.Tracer] = None


def get_tracer(name: str = "rpi-k8s-management") -> trace.Tracer:
    """Get or create a tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer(name)
    return _tracer


def traced(
    name: Optional[str] = None,
    attributes: Optional[dict[str, Any]] = None,
) -> Callable:
    """
    Decorator to trace a function execution.

    Args:
        name: Span name (defaults to function name)
        attributes: Additional span attributes

    Example:
        @traced("fetch_nodes")
        async def get_nodes():
            ...
    """

    def decorator(func: Callable) -> Callable:
        span_name = name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                # Add custom attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                # Add function info
                span.set_attribute("function.name", func.__name__)
                span.set_attribute("function.module", func.__module__)

                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                span.set_attribute("function.name", func.__name__)
                span.set_attribute("function.module", func.__module__)

                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class SpanContext:
    """Context manager for creating spans with additional utilities."""

    def __init__(
        self,
        name: str,
        attributes: Optional[dict[str, Any]] = None,
    ):
        """Initialize span context."""
        self.name = name
        self.attributes = attributes or {}
        self.span: Optional[trace.Span] = None

    def __enter__(self) -> trace.Span:
        """Enter span context."""
        tracer = get_tracer()
        self.span = tracer.start_span(self.name)
        self.span.__enter__()

        for key, value in self.attributes.items():
            self.span.set_attribute(key, value)

        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit span context."""
        if self.span:
            if exc_type:
                self.span.set_status(Status(StatusCode.ERROR, str(exc_val)))
                self.span.record_exception(exc_val)
            else:
                self.span.set_status(Status(StatusCode.OK))
            self.span.__exit__(exc_type, exc_val, exc_tb)
