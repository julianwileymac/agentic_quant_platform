"""Alpha Vantage enrichment PyFlink job.

Consumes ``alphavantage.quote.v1`` and broadcasts the companion
``alphavantage.overview.v1`` compacted stream so every quote can be joined
with the corresponding company overview (sector, industry, market cap, beta,
dividend yield, etc.). The enriched records are written to
``features.indicators.v1`` so the downstream trading stack can reuse the
existing indicator-compute topology.

Suspended by default in ``av-enrichment-job.yaml``; set ``spec.job.state:
running`` to enable. This job is additive and does not modify any existing
stream or topic.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Dict

from pyflink.common import Types, WatermarkStrategy  # type: ignore[import]
from pyflink.common.serialization import SimpleStringSchema  # type: ignore[import]
from pyflink.datastream import (  # type: ignore[import]
    BroadcastProcessFunction,
    MapFunction,
    StreamExecutionEnvironment,
)
from pyflink.datastream.connectors.kafka import (  # type: ignore[import]
    KafkaOffsetsInitializer,
    KafkaRecordSerializationSchema,
    KafkaSink,
    KafkaSource,
)
from pyflink.datastream.state import MapStateDescriptor  # type: ignore[import]


logger = logging.getLogger(__name__)


QUOTE_TOPIC = "alphavantage.quote.v1"
OVERVIEW_TOPIC = "alphavantage.overview.v1"
OUTPUT_TOPIC = "features.indicators.v1"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kafka.bootstrap.servers", dest="bootstrap", required=True)
    parser.add_argument("--kafka.group.id", dest="group_id", default="flink-av-enrichment")
    parser.add_argument("--parallelism", type=int, default=1)
    parser.add_argument("--checkpoint.interval.ms", dest="checkpoint_interval",
                        type=int, default=60_000)
    return parser.parse_args(argv)


class OverviewBroadcast(BroadcastProcessFunction):
    """Side-channel that keeps the latest overview per symbol."""

    def __init__(self, descriptor: MapStateDescriptor) -> None:
        self._descriptor = descriptor

    def process_broadcast_element(self, value, ctx):  # type: ignore[no-untyped-def]
        try:
            overview = json.loads(value)
        except json.JSONDecodeError:
            return
        symbol = (overview or {}).get("symbol")
        if not symbol:
            return
        state = ctx.get_broadcast_state(self._descriptor)
        state.put(str(symbol), json.dumps(overview))

    def process_element(self, value, ctx):  # type: ignore[no-untyped-def]
        try:
            quote = json.loads(value)
        except json.JSONDecodeError:
            return
        state = ctx.get_broadcast_state(self._descriptor)
        symbol = str(quote.get("symbol") or "")
        overview_raw = state.get(symbol) if symbol else None
        overview: Dict[str, Any] = {}
        if overview_raw:
            try:
                overview = json.loads(overview_raw)
            except json.JSONDecodeError:
                overview = {}
        enriched = {
            "symbol": symbol,
            "ts_ns": quote.get("ts_ns"),
            "price": quote.get("price"),
            "change": quote.get("change"),
            "change_percent": quote.get("change_percent"),
            "volume": quote.get("volume"),
            "sector": overview.get("sector"),
            "industry": overview.get("industry"),
            "market_capitalization": overview.get("market_capitalization"),
            "beta": overview.get("beta"),
            "dividend_yield": overview.get("dividend_yield"),
            "indicator": "av_enriched_quote",
            "source": "alphavantage",
        }
        yield json.dumps(enriched)


class EnsureJson(MapFunction):
    def map(self, value):  # type: ignore[no-untyped-def]
        try:
            json.loads(value)
            return value
        except (TypeError, json.JSONDecodeError):
            return "{}"


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.INFO)
    args = _parse_args(argv)
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(args.parallelism)
    env.enable_checkpointing(args.checkpoint_interval)

    # Quotes - keyed stream
    quote_source = (
        KafkaSource.builder()
        .set_bootstrap_servers(args.bootstrap)
        .set_topics(QUOTE_TOPIC)
        .set_group_id(args.group_id)
        .set_starting_offsets(KafkaOffsetsInitializer.latest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )
    quotes = env.from_source(
        quote_source,
        WatermarkStrategy.no_watermarks(),
        "av-quote-source",
        type_info=Types.STRING(),
    ).map(EnsureJson(), output_type=Types.STRING())

    # Overviews - broadcast stream (compacted topic = slow-moving)
    overview_source = (
        KafkaSource.builder()
        .set_bootstrap_servers(args.bootstrap)
        .set_topics(OVERVIEW_TOPIC)
        .set_group_id(f"{args.group_id}-overview")
        .set_starting_offsets(KafkaOffsetsInitializer.earliest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )
    descriptor = MapStateDescriptor("av-overview", Types.STRING(), Types.STRING())
    overviews = (
        env.from_source(
            overview_source,
            WatermarkStrategy.no_watermarks(),
            "av-overview-source",
            type_info=Types.STRING(),
        )
        .broadcast(descriptor)
    )

    enriched = quotes.connect(overviews).process(
        OverviewBroadcast(descriptor),
        output_type=Types.STRING(),
    )

    sink = (
        KafkaSink.builder()
        .set_bootstrap_servers(args.bootstrap)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(OUTPUT_TOPIC)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .build()
    )
    enriched.sink_to(sink).name("av-enriched-sink")

    env.execute("alphavantage-enrichment")


if __name__ == "__main__":
    main(sys.argv[1:])
