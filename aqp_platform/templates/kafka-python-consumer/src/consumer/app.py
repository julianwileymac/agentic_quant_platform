"""Async consumer application."""

from __future__ import annotations

import asyncio
import logging
import ssl
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional

from aiokafka import AIOKafkaConsumer
from opentelemetry import trace
from prometheus_client import Counter, Histogram, start_http_server

from .avro_codec import AvroCodec
from .config import ConsumerSettings
from .tracing import configure_tracing

logger = logging.getLogger(__name__)

MESSAGES_CONSUMED = Counter(
    "kafka_consumer_messages_consumed_total",
    "Kafka messages consumed.",
    ["topic", "status"],
)
PROCESS_LATENCY = Histogram(
    "kafka_consumer_process_seconds",
    "Latency of the user handler per record.",
    ["topic"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.1, 0.25, 1, 5),
)

Handler = Callable[[Dict[str, Any], Dict[str, Any]], Awaitable[None]]


@dataclass
class ConsumerApp:
    settings: ConsumerSettings
    handler: Handler
    codec: AvroCodec = field(init=False)
    consumer: AIOKafkaConsumer = field(init=False)
    tracer: trace.Tracer = field(init=False)

    def __post_init__(self) -> None:
        self.tracer = configure_tracing(self.settings.service_name, self.settings.otel_endpoint)
        self.codec = AvroCodec(self.settings.schema_registry_url, self.settings.schema_group)
        start_http_server(self.settings.metrics_port)

    def _ssl_context(self) -> Optional[ssl.SSLContext]:
        if self.settings.security_protocol.startswith("SASL_SSL") and self.settings.ssl_cafile:
            return ssl.create_default_context(cafile=self.settings.ssl_cafile)
        return None

    async def start(self) -> None:
        self.consumer = AIOKafkaConsumer(
            *self.settings.topics,
            bootstrap_servers=self.settings.bootstrap_servers,
            group_id=self.settings.group_id,
            auto_offset_reset=self.settings.auto_offset_reset,
            enable_auto_commit=self.settings.enable_auto_commit,
            max_poll_records=self.settings.max_poll_records,
            security_protocol=self.settings.security_protocol,
            sasl_mechanism=self.settings.sasl_mechanism,
            sasl_plain_username=self.settings.sasl_username,
            sasl_plain_password=self.settings.sasl_password,
            ssl_context=self._ssl_context(),
        )
        await self.consumer.start()

    async def stop(self) -> None:
        try:
            await self.consumer.stop()
        finally:
            await self.codec.close()

    async def run(self) -> None:
        try:
            async for msg in self.consumer:
                with self.tracer.start_as_current_span(
                    "kafka.consume",
                    attributes={
                        "messaging.system": "kafka",
                        "messaging.source.name": msg.topic,
                        "messaging.kafka.partition": msg.partition,
                        "messaging.kafka.offset": msg.offset,
                    },
                ) as span, PROCESS_LATENCY.labels(topic=msg.topic).time():
                    headers = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in (msg.headers or [])}
                    try:
                        record = await self.codec.decode(msg.value)
                    except Exception as exc:  # noqa: BLE001
                        span.record_exception(exc)
                        MESSAGES_CONSUMED.labels(topic=msg.topic, status="decode_error").inc()
                        continue
                    try:
                        await self.handler(record, headers)
                        MESSAGES_CONSUMED.labels(topic=msg.topic, status="ok").inc()
                    except Exception as exc:  # noqa: BLE001
                        span.record_exception(exc)
                        MESSAGES_CONSUMED.labels(topic=msg.topic, status="handler_error").inc()
                        continue
                    if not self.settings.enable_auto_commit:
                        await self.consumer.commit()
        finally:
            await self.stop()


async def _log_handler(record: Dict[str, Any], headers: Dict[str, Any]) -> None:
    logger.info("record=%s headers=%s", record, headers)


async def run_forever(settings: Optional[ConsumerSettings] = None, handler: Optional[Handler] = None) -> None:
    logging.basicConfig(level=logging.INFO)
    app = ConsumerApp(settings=settings or ConsumerSettings(), handler=handler or _log_handler)
    await app.start()
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    for sig in ("SIGTERM", "SIGINT"):
        try:
            loop.add_signal_handler(getattr(__import__("signal"), sig), stop_event.set)
        except NotImplementedError:
            pass

    run_task = asyncio.create_task(app.run())
    await stop_event.wait()
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass
    await app.stop()
