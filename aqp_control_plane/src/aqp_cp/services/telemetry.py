"""Telemetry streaming service — 10s polling + alert forwarding.

Maintains a per-service async generator on top of the active
provider's :meth:`InfrastructureProvider.stream_metrics`. Subscribers
receive :class:`MetricPoint` frames in real time; the supervisor also
detects CPU > ``alert_cpu_critical_pct`` and memory >
``alert_memory_critical_pct`` thresholds and emits
:class:`AlertEvent` frames to every connected operator.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

from aqp_cp.models import (
    AlertEvent,
    AlertSeverity,
    MetricPoint,
)
from aqp_cp.services.lifecycle import get_active_provider
from aqp_cp.settings import get_settings

logger = logging.getLogger(__name__)


class TelemetrySubscriber:
    """A single consumer's metric / alert queue.

    Backed by an :class:`asyncio.Queue` with a bounded capacity so a
    stuck consumer can't grow the supervisor's memory unbounded.
    """

    def __init__(self, queue_size: int = 1000) -> None:
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self.subscriber_id = str(uuid.uuid4())

    async def push(self, item: MetricPoint | AlertEvent) -> None:
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            # Drop the oldest, keep the newest — recency wins.
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            await self.queue.put(item)

    def __aiter__(self) -> "TelemetrySubscriber":
        return self

    async def __anext__(self) -> MetricPoint | AlertEvent:
        return await self.queue.get()


class TelemetrySupervisor:
    """Per-process telemetry broadcaster — single producer, many consumers.

    The supervisor spins one polling task per requested ``service_id``.
    Multiple subscribers for the same service share the producer.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[TelemetrySubscriber]] = {}
        self._producers: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._shutting_down = False

    async def subscribe(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
        interval_seconds: float | None = None,
    ) -> TelemetrySubscriber:
        sub = TelemetrySubscriber()
        async with self._lock:
            self._subscribers.setdefault(service_id, set()).add(sub)
            if service_id not in self._producers:
                self._producers[service_id] = asyncio.create_task(
                    self._produce(service_id, namespace=namespace, interval_seconds=interval_seconds)
                )
        return sub

    async def unsubscribe(self, service_id: str, sub: TelemetrySubscriber) -> None:
        async with self._lock:
            subs = self._subscribers.get(service_id)
            if subs:
                subs.discard(sub)
                if not subs:
                    task = self._producers.pop(service_id, None)
                    self._subscribers.pop(service_id, None)
                    if task is not None:
                        task.cancel()

    async def shutdown(self) -> None:
        self._shutting_down = True
        async with self._lock:
            tasks = list(self._producers.values())
            self._producers.clear()
            self._subscribers.clear()
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def _produce(
        self,
        service_id: str,
        *,
        namespace: str | None,
        interval_seconds: float | None,
    ) -> None:
        settings = get_settings()
        cpu_critical = settings.alert_cpu_critical_pct
        mem_critical = settings.alert_memory_critical_pct
        interval = interval_seconds or settings.telemetry_interval_seconds
        provider = get_active_provider()
        logger.info(
            "telemetry producer started service=%s provider=%s interval=%ss",
            service_id,
            provider.provider_alias,
            interval,
        )
        try:
            async for point in provider.stream_metrics(
                service_id, namespace=namespace, interval_seconds=interval
            ):
                await self._broadcast(service_id, point)
                if point.metric == "cpu_usage_pct" and point.value > cpu_critical:
                    await self._broadcast(
                        service_id,
                        _alert(
                            service_id=service_id,
                            provider=provider.provider_alias,
                            severity=AlertSeverity.CRITICAL,
                            title="CPU saturation",
                            message=(
                                f"CPU usage {point.value:.1f}% exceeded threshold "
                                f"{cpu_critical:.1f}% for service {service_id!r}"
                            ),
                            metric=point,
                        ),
                    )
                elif point.metric == "memory_usage_pct" and point.value > mem_critical:
                    await self._broadcast(
                        service_id,
                        _alert(
                            service_id=service_id,
                            provider=provider.provider_alias,
                            severity=AlertSeverity.CRITICAL,
                            title="Memory saturation",
                            message=(
                                f"Memory usage {point.value:.1f}% exceeded threshold "
                                f"{mem_critical:.1f}% for service {service_id!r}"
                            ),
                            metric=point,
                        ),
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "telemetry producer failed service=%s err=%s", service_id, exc, exc_info=True
            )

    async def _broadcast(self, service_id: str, item: MetricPoint | AlertEvent) -> None:
        async with self._lock:
            subs = list(self._subscribers.get(service_id, ()))
        for sub in subs:
            try:
                await sub.push(item)
            except Exception:  # noqa: BLE001
                pass


def _alert(
    *,
    service_id: str,
    provider: str,
    severity: AlertSeverity,
    title: str,
    message: str,
    metric: MetricPoint,
) -> AlertEvent:
    return AlertEvent(
        alert_id=str(uuid.uuid4()),
        service_id=service_id,
        provider=provider,
        severity=severity,
        title=title,
        message=message,
        timestamp=datetime.now(timezone.utc),
        metrics=[metric],
    )


_SUPERVISOR: TelemetrySupervisor | None = None
_INIT_LOCK = asyncio.Lock()


async def get_supervisor() -> TelemetrySupervisor:
    global _SUPERVISOR
    if _SUPERVISOR is None:
        async with _INIT_LOCK:
            if _SUPERVISOR is None:
                _SUPERVISOR = TelemetrySupervisor()
    return _SUPERVISOR


async def shutdown_supervisor() -> None:
    global _SUPERVISOR
    if _SUPERVISOR is not None:
        await _SUPERVISOR.shutdown()
        _SUPERVISOR = None


__all__ = [
    "TelemetrySubscriber",
    "TelemetrySupervisor",
    "get_supervisor",
    "shutdown_supervisor",
]
