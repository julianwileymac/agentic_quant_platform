"""Alpha Vantage producer application.

Boots an :class:`AlphaVantageClient`, registers every Avro schema with
Apicurio, then spawns one asyncio task per enabled stream. Each stream pulls
from the shared rate limiter via ``await client.<group>.amethod(...)``,
Avro-encodes the record, and hands it to a single shared confluent-kafka
``Producer`` instance. Failures are funnelled through
:func:`send_deadletter` which writes to ``alphavantage.deadletter.v1`` with a
typed ``error_kind``.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from pathlib import Path
from typing import Any, Dict, Optional

from confluent_kafka import KafkaError, Producer
from prometheus_client import Counter, Gauge, Histogram, start_http_server

from alphavantage_client import (
    AlphaVantageClient,
    AlphaVantageError,
    InvalidApiKeyError,
    InvalidSymbolError,
    PremiumEndpointError,
    RateLimitError,
    RateLimitKind,
    TransientError,
)
from alphavantage_client._errors import AlphaVantagePayloadError

from .avro_codec import AvroCodec
from .config import ProducerSettings, RuntimeConfig, load_runtime_config
from .tracing import configure_tracing, instrument_kafka_confluent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

MESSAGES = Counter(
    "alphavantage_producer_messages_total",
    "Messages produced by the AV producer.",
    ["stream", "topic", "status"],
)
API_REQUESTS = Histogram(
    "alphavantage_producer_api_request_seconds",
    "Latency of Alpha Vantage API calls made by the producer.",
    ["stream", "function"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)
RATE_LIMIT_TOKENS = Gauge(
    "alphavantage_producer_rate_limiter_tokens",
    "Tokens currently available in the AV rate limiter.",
)
RATE_LIMIT_MINUTE = Gauge(
    "alphavantage_producer_rate_limiter_requests_this_minute",
    "Requests served in the current rolling minute window.",
)
RATE_LIMIT_DAY = Gauge(
    "alphavantage_producer_rate_limiter_requests_today",
    "Requests served so far today (UTC).",
)
DEADLETTER = Counter(
    "alphavantage_producer_deadletter_total",
    "Messages pushed to the alphavantage.deadletter.v1 topic.",
    ["stream", "reason"],
)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------


class AlphaVantageProducerApp:
    def __init__(
        self,
        settings: ProducerSettings,
        runtime: RuntimeConfig,
        client: AlphaVantageClient,
        codec: AvroCodec,
        producer: Producer,
    ) -> None:
        self.settings = settings
        self.runtime = runtime
        self.client = client
        self.codec = codec
        self.producer = producer
        self.tracer = configure_tracing(settings.service_name, settings.otel_endpoint)
        instrument_kafka_confluent()
        self._shutdown = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        from . import streams  # local import to avoid a circular reference

        for name, cfg in self.runtime.streams.items():
            if not cfg.enabled:
                continue
            runner = streams.STREAMS.get(name)
            if runner is None:
                logger.warning("no runner registered for stream %s", name)
                continue
            task = asyncio.create_task(
                runner(self, cfg),
                name=f"stream:{name}",
            )
            self._tasks.append(task)

        metrics_task = asyncio.create_task(self._metrics_loop(), name="metrics-loop")
        self._tasks.append(metrics_task)

        if not self._tasks:
            logger.warning("no streams enabled; exiting")
            return

        await self._shutdown.wait()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def request_shutdown(self) -> None:
        logger.info("shutdown requested")
        self._shutdown.set()

    async def _metrics_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                snap = self.client.rate_limiter.snapshot()
                RATE_LIMIT_TOKENS.set(snap.tokens_available)
                RATE_LIMIT_MINUTE.set(snap.requests_this_minute)
                RATE_LIMIT_DAY.set(snap.requests_today)
            except Exception:  # pragma: no cover
                logger.debug("rate-limit snapshot failed", exc_info=True)
            await asyncio.sleep(5.0)

    # ------------------------------------------------------------------
    # Publication helpers
    # ------------------------------------------------------------------

    def publish(
        self,
        *,
        stream: str,
        topic: str,
        schema: str,
        record: Dict[str, Any],
        key: Optional[str] = None,
    ) -> None:
        labels = {"stream": stream, "topic": topic}
        try:
            payload = self.codec.encode(schema, record)
            self.producer.produce(
                topic=topic,
                key=key.encode("utf-8") if key else None,
                value=payload,
                on_delivery=_delivery_callback(stream, topic),
            )
            self.producer.poll(0)
            MESSAGES.labels(status="queued", **labels).inc()
        except Exception as exc:  # noqa: BLE001
            logger.exception("publish failed stream=%s topic=%s", stream, topic)
            MESSAGES.labels(status="error", **labels).inc()
            self.send_deadletter(
                stream=stream,
                target_topic=topic,
                av_function=record.get("av_function", "UNKNOWN"),
                error_kind="PRODUCER_FAILURE",
                error_message=str(exc),
                request_params={"schema": schema},
                raw_response=None,
            )

    def send_deadletter(
        self,
        *,
        stream: str,
        target_topic: str,
        av_function: str,
        error_kind: str,
        error_message: Optional[str] = None,
        raw_response: Optional[str] = None,
        retry_after_seconds: Optional[float] = None,
        request_params: Optional[Dict[str, Any]] = None,
        attempt_count: int = 1,
    ) -> None:
        DEADLETTER.labels(stream=stream, reason=error_kind).inc()
        try:
            record = {
                "ts_ns": _ns(),
                "target_topic": target_topic,
                "av_function": av_function,
                "request_params": {
                    str(k): str(v)
                    for k, v in (request_params or {}).items()
                },
                "error_kind": error_kind,
                "error_message": error_message,
                "raw_response": raw_response,
                "retry_after_seconds": retry_after_seconds,
                "attempt_count": attempt_count,
                "producer": self.settings.client_id,
                "ingest_ts_ns": _ns(),
            }
            payload = self.codec.encode("alphavantage_deadletter_v1", record)
            self.producer.produce(
                topic=self.settings.topic_deadletter,
                key=av_function.encode("utf-8"),
                value=payload,
            )
            self.producer.poll(0)
        except Exception:  # noqa: BLE001
            logger.exception("deadletter publish failed stream=%s", stream)


def _delivery_callback(stream: str, topic: str):
    def _on_delivery(err: Optional[KafkaError], msg: Any) -> None:
        labels = {"stream": stream, "topic": topic}
        if err is not None:
            logger.error("delivery failed stream=%s topic=%s err=%s", stream, topic, err)
            MESSAGES.labels(status="delivery_error", **labels).inc()
        else:
            MESSAGES.labels(status="delivered", **labels).inc()
    return _on_delivery


def _ns() -> int:
    return time.time_ns()


# ---------------------------------------------------------------------------
# Bootstrap helpers
# ---------------------------------------------------------------------------


def build_kafka_producer(settings: ProducerSettings) -> Producer:
    cfg: Dict[str, Any] = {
        "bootstrap.servers": settings.bootstrap_servers,
        "client.id": settings.client_id,
        "enable.idempotence": True,
        "acks": "all",
        "compression.type": "snappy",
        "linger.ms": 10,
        "security.protocol": settings.security_protocol,
    }
    if settings.security_protocol.startswith("SASL"):
        cfg["sasl.mechanism"] = settings.sasl_mechanism
        cfg["sasl.username"] = settings.sasl_username
        pw = settings.resolve_sasl_password()
        if pw:
            cfg["sasl.password"] = pw
        if settings.ssl_ca_location:
            cfg["ssl.ca.location"] = settings.ssl_ca_location
    return Producer(cfg)


def build_client(settings: ProducerSettings) -> AlphaVantageClient:
    return AlphaVantageClient(
        api_key=settings.av_api_key,
        api_key_file=settings.av_api_key_file,
        base_url=settings.av_base_url,
        rate_limit_rpm=settings.av_rpm_limit,
        daily_limit=settings.av_daily_limit,
        timeout_seconds=settings.av_timeout_seconds,
        max_retries=settings.av_max_retries,
        cache_backend="memory",
    )


def load_schemas(settings: ProducerSettings, codec: AvroCodec) -> None:
    schema_dir = Path(settings.schema_dir)
    if not schema_dir.exists():
        logger.warning("schema dir %s missing; codec will fail on encode", schema_dir)
        return
    for path in sorted(schema_dir.glob("alphavantage_*.avsc")):
        name = path.stem
        try:
            codec.register_from_file(name, path)
            logger.info("registered schema %s", name)
        except Exception:  # noqa: BLE001
            logger.exception("schema registration failed for %s", name)


async def run_app(settings: Optional[ProducerSettings] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = settings or ProducerSettings()
    runtime = load_runtime_config(settings.config_file)
    start_http_server(settings.metrics_port)
    client = build_client(settings)
    codec = AvroCodec(
        settings.schema_registry_url,
        group=settings.schema_group,
        auto_register=settings.register_schemas_on_start,
    )
    load_schemas(settings, codec)
    producer = build_kafka_producer(settings)

    app = AlphaVantageProducerApp(settings, runtime, client, codec, producer)
    loop = asyncio.get_running_loop()

    def _signal_handler() -> None:
        app.request_shutdown()

    try:
        loop.add_signal_handler(signal.SIGTERM, _signal_handler)
        loop.add_signal_handler(signal.SIGINT, _signal_handler)
    except NotImplementedError:  # pragma: no cover - Windows dev path
        pass

    try:
        await app.run()
    finally:
        producer.flush(15.0)
        codec.close()
        await client.aclose()


def classify_av_error(exc: Exception) -> str:
    if isinstance(exc, InvalidApiKeyError):
        return "INVALID_KEY"
    if isinstance(exc, InvalidSymbolError):
        return "INVALID_SYMBOL"
    if isinstance(exc, PremiumEndpointError):
        return "PREMIUM_REQUIRED"
    if isinstance(exc, RateLimitError):
        if exc.kind == RateLimitKind.DAILY:
            return "RATE_LIMIT_DAILY"
        if exc.kind == RateLimitKind.RPM:
            return "RATE_LIMIT_RPM"
    if isinstance(exc, TransientError):
        return "TRANSIENT"
    if isinstance(exc, AlphaVantagePayloadError):
        return "PAYLOAD_ERROR"
    if isinstance(exc, AlphaVantageError):
        return "UNKNOWN"
    return "UNKNOWN"


__all__ = [
    "AlphaVantageProducerApp",
    "build_client",
    "build_kafka_producer",
    "classify_av_error",
    "load_schemas",
    "run_app",
]
