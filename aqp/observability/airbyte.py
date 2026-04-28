"""Tracing helpers for Airbyte control-plane operations."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from aqp.observability.tracing import get_tracer


@contextmanager
def airbyte_span(name: str, **attributes: Any) -> Iterator[Any]:
    """Create a best-effort Airbyte tracing span."""
    tracer = get_tracer("aqp.airbyte")
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            if value is None:
                continue
            try:
                span.set_attribute(f"airbyte.{key}", value)
            except Exception:
                pass
        yield span


__all__ = ["airbyte_span"]
