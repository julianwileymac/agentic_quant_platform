"""Scanner-alert PyFlink job.

Joins IBKR scanner rows (``market.scanner.v1``) with recent bars
(``market.bar.v1``) so the pipeline can promote high-rank instruments
into trade signals. The output is written to ``features.signals.v1``
and tagged with ``source_job=scanner_alert`` so strategies can filter
on it.

The join is a simple one-sided interval join on ``vt_symbol``:

- Scanner events are cached in keyed state for 10 minutes.
- Whenever a bar arrives for a symbol we checked in the last cycle and
  it moved in the scanner's direction (gain + positive return, or
  loss + negative return), we emit a ``Signal``.
"""
from __future__ import annotations

import argparse
import json
import logging
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


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--kafka.bootstrap.servers", dest="bootstrap", required=True)
    p.add_argument("--kafka.group.id", dest="group_id", default="flink-scanner-alert")
    p.add_argument("--kafka.sink.topic", dest="sink_topic", default="features.signals.v1")
    p.add_argument("--parallelism", type=int, default=1)
    p.add_argument("--checkpoint.interval.ms", dest="checkpoint_interval", type=int, default=60_000)
    return p.parse_args(argv)


class JoinFunction(KeyedProcessFunction):
    def __init__(self) -> None:
        self._scan_state = None

    def open(self, ctx: RuntimeContext) -> None:
        ttl = (
            StateTtlConfig.new_builder(Time.minutes(10))
            .set_update_type(StateTtlConfig.UpdateType.OnCreateAndWrite)
            .build()
        )
        desc = ValueStateDescriptor("scanner_row", Types.STRING())
        desc.enable_time_to_live(ttl)
        self._scan_state = ctx.get_state(desc)

    def process_element(self, value, ctx):  # type: ignore[no-untyped-def]
        topic, payload = value
        try:
            record = json.loads(payload)
        except Exception:  # noqa: BLE001
            logger.exception("scanner decode failed")
            return

        if topic == "market.scanner.v1":
            self._scan_state.update(json.dumps(record))
            return

        scan_raw = self._scan_state.value()
        if not scan_raw:
            return
        scan = json.loads(scan_raw)
        rank = int(scan.get("rank", 99))
        scan_code = str(scan.get("scan_code", ""))

        if topic != "market.bar.v1":
            return

        close = float(record.get("close", 0.0) or 0.0)
        open_ = float(record.get("open", close))
        if open_ == 0:
            return
        move = (close - open_) / open_

        if scan_code.startswith("TOP_PERC_GAIN") and move > 0.002:
            direction = "long"
            strength = min(1.0, move * 20 + (25 - rank) / 25)
        elif scan_code.startswith("TOP_PERC_LOSE") and move < -0.002:
            direction = "short"
            strength = min(1.0, abs(move) * 20 + (25 - rank) / 25)
        elif scan_code.startswith("HOT_BY_VOLUME") and abs(move) > 0.004:
            direction = "long" if move > 0 else "short"
            strength = min(1.0, abs(move) * 15 + (25 - rank) / 25)
        else:
            return

        yield json.dumps(
            {
                "ts_ns": int(record.get("ts_ns", time.time_ns())),
                "vt_symbol": record["vt_symbol"],
                "strength": float(strength),
                "direction": direction,
                "confidence": max(0.0, (25 - rank) / 25),
                "horizon_sec": 900,
                "source_job": "scanner_alert",
                "rationale": f"{scan_code} rank={rank} move={move:.4f}",
                "features_ref": None,
            }
        )


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
        .set_topics("market.scanner.v1", "market.bar.v1")
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
    sink = (
        KafkaSink.builder()
        .set_bootstrap_servers(args.bootstrap)
        .set_record_serializer(sink_ser)
        .set_transactional_id_prefix("flink-scanner-alert-")
        .build()
    )

    stream = env.from_source(source, WatermarkStrategy.no_watermarks(), "scanner-and-bars")
    # The source doesn't expose the topic to the DataStream, so we encode it
    # on the record itself downstream -- MVP: treat every payload as bar and
    # fall back to scanner if the parsed JSON has ``scan_code``. Production
    # clients should prefix the value with the topic or use record metadata.
    def _split_topic(payload: str):
        try:
            data = json.loads(payload)
        except Exception:
            return ("market.bar.v1", payload)
        topic = "market.scanner.v1" if "scan_code" in data else "market.bar.v1"
        return (topic, payload)

    (
        stream.map(_split_topic, output_type=Types.TUPLE([Types.STRING(), Types.STRING()]))
        .key_by(lambda x: json.loads(x[1]).get("vt_symbol", ""))
        .process(JoinFunction())
        .sink_to(sink)
    )

    env.execute("aqp-scanner-alert")


if __name__ == "__main__":
    main()
