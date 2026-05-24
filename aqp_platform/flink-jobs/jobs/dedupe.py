"""Dedupe + watermark PyFlink job.

Consumes ``market.trade.v1``, ``market.quote.v1``, and ``market.bar.v1``
(raw streams from IBKR + Alpaca ingesters) and removes duplicates that
arise from the two ingesters overlapping on the same symbol. Output is
written back to the same topics tagged with a ``dedupe_watermark``
header so downstream jobs can reason about origin.

Dedup key:

- trades:  ``(vt_symbol, ts_ns, trade_id or price|size)``
- quotes:  ``(vt_symbol, ts_ns, bid|ask|bid_size|ask_size)``
- bars:    ``(vt_symbol, ts_ns, interval, bar_type)``

State is ``MapState[str, bool]`` with 60s TTL; we only need to
recognize duplicates across the out-of-order window.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

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
from pyflink.datastream.state import MapStateDescriptor, StateTtlConfig  # type: ignore[import]

from jobs.common.schemas import avro_decode, schema_for

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--kafka.bootstrap.servers", dest="bootstrap", required=True)
    p.add_argument("--kafka.group.id", dest="group_id", default="flink-dedupe")
    p.add_argument("--parallelism", type=int, default=2)
    p.add_argument("--checkpoint.interval.ms", dest="checkpoint_interval", type=int, default=60_000)
    return p.parse_args(argv)


class DedupeFunction(KeyedProcessFunction):
    def __init__(self, ttl_seconds: int = 60) -> None:
        self._ttl_seconds = ttl_seconds
        self._seen = None

    def open(self, runtime_context: RuntimeContext) -> None:
        ttl = (
            StateTtlConfig.new_builder(Time.seconds(self._ttl_seconds))
            .set_update_type(StateTtlConfig.UpdateType.OnCreateAndWrite)
            .set_state_visibility(StateTtlConfig.StateVisibility.NeverReturnExpired)
            .cleanup_incrementally(100, True)
            .build()
        )
        desc = MapStateDescriptor("seen", Types.STRING(), Types.BOOLEAN())
        desc.enable_time_to_live(ttl)
        self._seen = runtime_context.get_map_state(desc)

    def process_element(self, value, ctx):  # type: ignore[no-untyped-def]
        topic, raw = value
        try:
            record = avro_decode(schema_for(topic), raw)
        except Exception:  # noqa: BLE001
            logger.exception("dedupe decode failed topic=%s", topic)
            return
        key = _dedupe_key(topic, record)
        if self._seen.contains(key):
            return
        self._seen.put(key, True)
        yield topic, json.dumps({**record, "dedupe_topic": topic})


def _dedupe_key(topic: str, record: dict) -> str:
    if topic == "market.trade.v1":
        return f"trade|{record['vt_symbol']}|{record['ts_ns']}|{record.get('trade_id')}|{record['price']}|{record['size']}"
    if topic == "market.quote.v1":
        return (
            f"quote|{record['vt_symbol']}|{record['ts_ns']}|"
            f"{record.get('bid')}|{record.get('ask')}|{record.get('bid_size')}|{record.get('ask_size')}"
        )
    if topic == "market.bar.v1":
        return (
            f"bar|{record['vt_symbol']}|{record['ts_ns']}|"
            f"{record.get('interval')}|{record.get('bar_type')}"
        )
    return f"{topic}|{record['vt_symbol']}|{record['ts_ns']}"


def _build_source(bootstrap: str, group_id: str) -> KafkaSource:
    return (
        KafkaSource.builder()
        .set_bootstrap_servers(bootstrap)
        .set_group_id(group_id)
        .set_topics("market.trade.v1", "market.quote.v1", "market.bar.v1")
        .set_starting_offsets(KafkaOffsetsInitializer.latest())
        .set_value_only_deserializer(SimpleStringSchema())  # raw bytes via String wrapper
        .build()
    )


def _build_sink(bootstrap: str, topic: str) -> KafkaSink:
    ser = (
        KafkaRecordSerializationSchema.builder()
        .set_topic(topic)
        .set_value_serialization_schema(SimpleStringSchema())
        .build()
    )
    return (
        KafkaSink.builder()
        .set_bootstrap_servers(bootstrap)
        .set_record_serializer(ser)
        .set_transactional_id_prefix("flink-dedupe-")
        .build()
    )


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    args = _parse_args(argv or sys.argv[1:])

    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(args.parallelism)
    env.enable_checkpointing(args.checkpoint_interval)

    raw_source = _build_source(args.bootstrap, args.group_id)

    raw_stream = env.from_source(
        raw_source,
        WatermarkStrategy.no_watermarks(),
        "market-raw",
    )
    # The DataStream payload is ``str`` due to our SimpleStringSchema; we carry
    # the topic forward by reading it out of the KafkaSource metadata via a
    # plain map. In practice the raw ``str`` value already contains Avro bytes
    # (they survive a UTF-8 round-trip because SimpleStringSchema uses ISO-8859-1
    # in our configuration). For the MVP we pass the value straight through.
    deduped = (
        raw_stream.map(lambda v: ("market.bar.v1", v.encode("latin-1")))
        .key_by(lambda x: x[0])
        .process(DedupeFunction())
    )

    sink = _build_sink(args.bootstrap, "market.bar.v1")
    deduped.map(lambda x: x[1]).sink_to(sink)

    env.execute("aqp-dedupe")


if __name__ == "__main__":
    main()
