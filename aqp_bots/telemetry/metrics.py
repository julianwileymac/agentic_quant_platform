"""Prometheus metrics for QuantBot bots.

Explicit histogram buckets cover the full HFT-to-EOD latency range
(blueprint §J.3):

::

    [1µs, 5µs, 10µs, 50µs, 100µs, 500µs, 1ms, 5ms, 10ms, 100ms, 1s, +Inf]

Standard metrics:

- ``quantbot_orders_total{variant, venue, status}``
- ``quantbot_orders_rejected_total{variant, venue, reason}``
- ``quantbot_tick_to_trade_seconds`` — histogram with HFT buckets
- ``quantbot_realized_pnl_usd{variant}``
- ``quantbot_unrealized_pnl_usd{variant}``
- ``quantbot_queue_depth{topic}``
- ``quantbot_reconcile_mismatch_count{venue}``
- ``quantbot_risk_blocks_total{policy, citation}``
- ``quantbot_kill_switch_engagements_total{scope}``

Falls back to a no-op surface when ``prometheus_client`` isn't
installed.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


HFT_LATENCY_BUCKETS: tuple[float, ...] = (
    1e-6,    # 1µs
    5e-6,
    1e-5,
    5e-5,
    1e-4,
    5e-4,
    1e-3,    # 1ms
    5e-3,
    1e-2,
    1e-1,
    1.0,
    float("inf"),
)


class _NoopMetric:
    def labels(self, **_: Any) -> "_NoopMetric": return self
    def inc(self, *a: Any, **kw: Any) -> None: return
    def set(self, *a: Any, **kw: Any) -> None: return
    def observe(self, *a: Any, **kw: Any) -> None: return


class QuantBotMetrics:
    """Prometheus client facade.

    Lazy-built; the kernel calls :func:`get_metrics` once and re-uses
    the singleton.
    """

    def __init__(self) -> None:
        self._enabled: bool = False
        self._init_metrics()

    def _init_metrics(self) -> None:
        try:
            from prometheus_client import Counter, Gauge, Histogram  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001
            self.orders_total = _NoopMetric()
            self.orders_rejected_total = _NoopMetric()
            self.tick_to_trade_seconds = _NoopMetric()
            self.realized_pnl_usd = _NoopMetric()
            self.unrealized_pnl_usd = _NoopMetric()
            self.queue_depth = _NoopMetric()
            self.reconcile_mismatch_count = _NoopMetric()
            self.risk_blocks_total = _NoopMetric()
            self.kill_switch_engagements_total = _NoopMetric()
            return

        self._enabled = True
        self.orders_total = Counter(
            "quantbot_orders_total",
            "Total orders placed (per variant/venue/status)",
            ["variant", "venue", "status"],
        )
        self.orders_rejected_total = Counter(
            "quantbot_orders_rejected_total",
            "Orders rejected by pre-trade risk or the venue",
            ["variant", "venue", "reason"],
        )
        self.tick_to_trade_seconds = Histogram(
            "quantbot_tick_to_trade_seconds",
            "End-to-end latency from inbound tick to outbound order (seconds)",
            ["variant", "venue"],
            buckets=HFT_LATENCY_BUCKETS,
        )
        self.realized_pnl_usd = Gauge(
            "quantbot_realized_pnl_usd",
            "Realised PnL in USD per variant",
            ["variant", "bot_id"],
        )
        self.unrealized_pnl_usd = Gauge(
            "quantbot_unrealized_pnl_usd",
            "Unrealised PnL in USD per variant",
            ["variant", "bot_id"],
        )
        self.queue_depth = Gauge(
            "quantbot_queue_depth",
            "Kernel bus queue depth by topic",
            ["topic"],
        )
        self.reconcile_mismatch_count = Counter(
            "quantbot_reconcile_mismatch_count",
            "Number of reconciliation mismatches by venue",
            ["venue"],
        )
        self.risk_blocks_total = Counter(
            "quantbot_risk_blocks_total",
            "Pre-trade risk blocks broken down by policy + citation",
            ["policy", "citation"],
        )
        self.kill_switch_engagements_total = Counter(
            "quantbot_kill_switch_engagements_total",
            "Kill switch engagements by scope",
            ["scope"],
        )

    @property
    def enabled(self) -> bool:
        return self._enabled


_INSTANCE: QuantBotMetrics | None = None


def get_metrics() -> QuantBotMetrics:
    """Return the process-wide singleton."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = QuantBotMetrics()
    return _INSTANCE


__all__ = ["HFT_LATENCY_BUCKETS", "QuantBotMetrics", "get_metrics"]
