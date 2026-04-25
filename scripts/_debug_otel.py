"""One-shot diagnostic script: verify the API module sets up OTel correctly."""
from __future__ import annotations


def main() -> None:
    import aqp.api.main as main_module  # noqa: F401 — triggers module-level init

    from opentelemetry import trace

    from aqp.observability.tracing import _instrumented, _tracer_provider

    provider = trace.get_tracer_provider()
    print("global provider:", type(provider).__name__)
    print("aqp tracer provider:", type(_tracer_provider).__name__ if _tracer_provider else None)
    print("instrumented:", sorted(_instrumented))

    # Try emitting a span end-to-end.
    tracer = trace.get_tracer("debug")
    with tracer.start_as_current_span("debug.probe") as span:
        span.set_attribute("debug.ok", True)
    if _tracer_provider is not None:
        _tracer_provider.force_flush(timeout_millis=2000)
        print("flushed")


if __name__ == "__main__":
    main()
