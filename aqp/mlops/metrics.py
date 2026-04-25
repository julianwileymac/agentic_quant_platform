"""Prometheus metric primitives for AQP training, backtesting, and serving.

Metrics are lazily imported so ``prometheus_client`` stays optional. All
helpers degrade to a no-op (returning a dummy object) when the library
isn't available, which keeps the rest of the platform resilient.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)


class _NoopMetric:
    def labels(self, *_: Any, **__: Any) -> _NoopMetric:
        return self

    def inc(self, _: float = 1.0) -> None:
        return None

    def set(self, _: float) -> None:
        return None

    def observe(self, _: float) -> None:
        return None


def _try_import() -> Any | None:
    try:
        import prometheus_client

        return prometheus_client
    except Exception:
        return None


_prom = _try_import()


def _counter(name: str, docs: str, labelnames: tuple[str, ...] = ()) -> Any:
    if _prom is None:
        return _NoopMetric()
    try:
        return _prom.Counter(name, docs, labelnames)
    except Exception:
        return _NoopMetric()


def _gauge(name: str, docs: str, labelnames: tuple[str, ...] = ()) -> Any:
    if _prom is None:
        return _NoopMetric()
    try:
        return _prom.Gauge(name, docs, labelnames)
    except Exception:
        return _NoopMetric()


def _histogram(name: str, docs: str, labelnames: tuple[str, ...] = ()) -> Any:
    if _prom is None:
        return _NoopMetric()
    try:
        return _prom.Histogram(name, docs, labelnames)
    except Exception:
        return _NoopMetric()


# Platform-wide metric registry (import-time singletons).
TRAIN_DURATION = _histogram(
    "aqp_train_duration_seconds",
    "Wall-clock time spent training a model.",
    ("model_class",),
)

BACKTEST_DURATION = _histogram(
    "aqp_backtest_duration_seconds",
    "Wall-clock time spent in backtest.runner.",
    ("engine", "strategy"),
)

BACKTEST_SHARPE = _gauge(
    "aqp_backtest_sharpe",
    "Annualised Sharpe ratio of the most recent backtest per strategy.",
    ("strategy",),
)

PAPER_PNL = _gauge(
    "aqp_paper_pnl",
    "Running realised PnL of the live paper trading session.",
    ("strategy", "account"),
)

SERVE_REQUESTS = _counter(
    "aqp_serve_requests_total",
    "Inference requests served broken down by backend.",
    ("backend", "model_name"),
)

SERVE_LATENCY = _histogram(
    "aqp_serve_latency_seconds",
    "Latency of model-serving requests.",
    ("backend", "model_name"),
)


@contextmanager
def time_histogram(metric: Any, *labels: Any):
    """Time a block of code and ``observe()`` it on ``metric.labels(*labels)``."""
    import time

    start = time.perf_counter()
    try:
        yield
    finally:
        try:
            elapsed = time.perf_counter() - start
            metric.labels(*labels).observe(elapsed) if labels else metric.observe(elapsed)
        except Exception:
            logger.debug("time_histogram observe failed", exc_info=True)


__all__ = [
    "BACKTEST_DURATION",
    "BACKTEST_SHARPE",
    "PAPER_PNL",
    "SERVE_LATENCY",
    "SERVE_REQUESTS",
    "TRAIN_DURATION",
    "time_histogram",
]
