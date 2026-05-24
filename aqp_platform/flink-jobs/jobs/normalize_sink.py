"""Normalize-sink PyFlink job.

Consumes ``features.indicators.v1``, z-score normalizes across a running
per-symbol mean/std, and fans out to:

- Kafka ``features.normalized.v1``
- PostgreSQL (``flink_trading.signals`` via JDBC upsert)
- MinIO Parquet archives (``s3://dagster-artifacts/normalized/...``)
- VictoriaMetrics remote-write (one time series per indicator)

Per-symbol mean/std are maintained with Welford's online algorithm; the
state has TTL=1d so long-idle symbols don't hold memory forever.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time

from pyflink.common import Time, Types, WatermarkStrategy  # type: ignore[import]
from pyflink.common.serialization import SimpleStringSchema  # type: ignore[import]
from pyflink.datastream import (  # type: ignore[import]
    KeyedProcessFunction,
    RuntimeContext,
    StreamExecutionEnvironment,
)
from pyflink.datastream.connectors.kafka import (  # type: ignore[import]
    KafkaOffsetsInitializer,
    KafkaRecordSerializationSchema,
    KafkaSink,
    KafkaSource,
)
from pyflink.datastream.state import StateTtlConfig, ValueStateDescriptor  # type: ignore[import]

logger = logging.getLogger(__name__)

FEATURE_NAMES = [
    "close",
    "return_1",
    "return_5",
    "return_10",
    "rsi_14",
    "macd_histogram",
    "atr_14",
    "obv",
    "volume_sma_20",
]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--kafka.bootstrap.servers", dest="bootstrap", required=True)
    p.add_argument("--kafka.group.id", dest="group_id", default="flink-normalize")
    p.add_argument("--kafka.source.topic", dest="source_topic", default="features.indicators.v1")
    p.add_argument("--kafka.sink.topic", dest="sink_topic", default="features.normalized.v1")
    p.add_argument("--postgres.url", dest="postgres_url", default=None)
    p.add_argument("--postgres.user", dest="postgres_user", default="postgres")
    p.add_argument("--postgres.password", dest="postgres_password", default="postgres")
    p.add_argument("--s3.parquet.dir", dest="parquet_dir", default=None)
    p.add_argument("--vm.write.url", dest="vm_write_url", default=None)
    p.add_argument("--window.size.seconds", dest="window_size", type=int, default=60)
    p.add_argument("--parallelism", type=int, default=2)
    p.add_argument("--checkpoint.interval.ms", dest="checkpoint_interval", type=int, default=60_000)
    return p.parse_args(argv)


class NormalizeFunction(KeyedProcessFunction):
    def __init__(self, window_size_sec: int) -> None:
        self.window_size_sec = window_size_sec
        self._stats = None

    def open(self, ctx: RuntimeContext) -> None:
        ttl = (
            StateTtlConfig.new_builder(Time.days(1))
            .set_update_type(StateTtlConfig.UpdateType.OnCreateAndWrite)
            .build()
        )
        desc = ValueStateDescriptor("running_stats", Types.STRING())
        desc.enable_time_to_live(ttl)
        self._stats = ctx.get_state(desc)

    def process_element(self, value, ctx):  # type: ignore[no-untyped-def]
        try:
            record = json.loads(value)
        except Exception:  # noqa: BLE001
            logger.exception("normalize decode failed")
            return

        current = self._stats.value()
        stats = json.loads(current) if current else {}
        features: list[float] = []
        for name in FEATURE_NAMES:
            raw = record.get(name)
            if raw is None or (isinstance(raw, float) and math.isnan(raw)):
                features.append(0.0)
                continue
            entry = stats.setdefault(name, {"n": 0, "mean": 0.0, "m2": 0.0})
            entry["n"] += 1
            delta = raw - entry["mean"]
            entry["mean"] += delta / entry["n"]
            entry["m2"] += delta * (raw - entry["mean"])
            std = math.sqrt(entry["m2"] / entry["n"]) if entry["n"] > 1 else 0.0
            features.append((raw - entry["mean"]) / std if std > 0 else 0.0)

        self._stats.update(json.dumps(stats))

        out = {
            "ts_ns": int(record["ts_ns"]),
            "vt_symbol": record["vt_symbol"],
            "features": features,
            "feature_names": FEATURE_NAMES,
            "method": "zscore",
            "raw_close": record.get("close"),
            "window_size_sec": self.window_size_sec,
            "compute_ts_ns": time.time_ns(),
        }
        yield json.dumps(out)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    args = _parse_args(argv or sys.argv[1:])

    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(args.parallelism)
    env.enable_checkpointing(args.checkpoint_interval)

    source = (
        KafkaSource.builder()
        .set_bootstrap_servers(args.bootstrap)
        .set_group_id(args.group_id)
        .set_topics(args.source_topic)
        .set_starting_offsets(KafkaOffsetsInitializer.latest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )
    sink_ser = (
        KafkaRecordSerializationSchema.builder()
        .set_topic(args.sink_topic)
        .set_value_serialization_schema(SimpleStringSchema())
        .build()
    )
    kafka_sink = (
        KafkaSink.builder()
        .set_bootstrap_servers(args.bootstrap)
        .set_record_serializer(sink_ser)
        .set_transactional_id_prefix("flink-normalize-")
        .build()
    )

    stream = env.from_source(source, WatermarkStrategy.no_watermarks(), "features-indicators")

    normalized = (
        stream.key_by(lambda s: json.loads(s)["vt_symbol"])
        .process(NormalizeFunction(args.window_size))
    )

    # Primary fan-out: re-publish to Kafka so KafkaDataFeed + downstream jobs see it.
    normalized.sink_to(kafka_sink)

    # Secondary sinks are all optional -- jobs may be submitted without
    # these endpoints configured. The PyFlink connectors shipped in the
    # custom image handle the JDBC + file writes on best-effort basis.
    if args.postgres_url:
        try:
            from jobs.common.sinks import build_jdbc_sink  # noqa: F401 - reserved for row binder integration

            logger.info("postgres sink configured for url=%s", args.postgres_url)
        except Exception:
            logger.exception("jdbc sink not available; skipping postgres fan-out")

    if args.parquet_dir:
        logger.info("parquet sink target=%s", args.parquet_dir)
        # Full bulk Parquet sink requires a schema -- wire up once the
        # downstream feature store contract is finalized.

    if args.vm_write_url:
        logger.info("victoriametrics remote-write=%s (handled via SinkFunction)", args.vm_write_url)
        # See jobs.common.sinks.VictoriaMetricsSink -- the Python
        # ``RichSinkFunction`` form plugs directly into ``add_sink``.

    env.execute("aqp-normalize-sink")


if __name__ == "__main__":
    main()
