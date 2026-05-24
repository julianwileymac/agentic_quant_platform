"""Indicator-computation PyFlink job.

Consumes ``market.bar.v1``, keys by ``vt_symbol``, maintains a rolling
price window per symbol, and emits ``features.indicators.v1`` records
on every new bar. Indicators: SMA 5/10/20/50, EMA 12/26, RSI 14,
MACD (line+signal+histogram), Bollinger Bands (20), ATR 14, VWAP,
volume SMA 20, OBV, lagged prices/volumes/returns.

For this MVP we run stateful-per-key with a ``ListState`` holding the
last N closes. The TaskManager image already includes numpy / pandas so
the computations stay compact.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import deque
from typing import Any, Deque

import numpy as np
from pyflink.common import Types, WatermarkStrategy  # type: ignore[import]
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
from pyflink.datastream.state import ListStateDescriptor  # type: ignore[import]

from jobs.common.schemas import avro_decode

logger = logging.getLogger(__name__)

MAX_HISTORY = 60  # enough for SMA 50 + a little buffer


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--kafka.bootstrap.servers", dest="bootstrap", required=True)
    p.add_argument("--kafka.group.id", dest="group_id", default="flink-indicators")
    p.add_argument("--kafka.source.topic", dest="source_topic", default="market.bar.v1")
    p.add_argument("--kafka.sink.topic", dest="sink_topic", default="features.indicators.v1")
    p.add_argument("--window.size.seconds", dest="window_size", type=int, default=60)
    p.add_argument("--parallelism", type=int, default=2)
    p.add_argument("--checkpoint.interval.ms", dest="checkpoint_interval", type=int, default=60_000)
    return p.parse_args(argv)


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    diffs = np.diff(np.asarray(closes[-(period + 1) :], dtype=float))
    gains = diffs[diffs > 0].sum() / period
    losses = -diffs[diffs < 0].sum() / period
    if losses == 0:
        return 100.0
    rs = gains / losses
    return float(100.0 - (100.0 / (1.0 + rs)))


def _ema(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    arr = np.asarray(closes[-period:], dtype=float)
    # Simple EMA using pandas-less convolution; the TaskManager image has pandas too
    multiplier = 2.0 / (period + 1)
    ema = arr[0]
    for price in arr[1:]:
        ema = (price - ema) * multiplier + ema
    return float(ema)


def _compute_indicators(
    vt_symbol: str,
    closes: list[float],
    volumes: list[float],
    highs: list[float],
    lows: list[float],
    window_ns: int,
    window_size_sec: int,
) -> dict[str, Any]:
    close = closes[-1]
    record: dict[str, Any] = {
        "ts_ns": window_ns,
        "window_start_ns": window_ns - window_size_sec * 1_000_000_000,
        "window_size_sec": window_size_sec,
        "vt_symbol": vt_symbol,
        "close": close,
        "compute_ts_ns": time.time_ns(),
    }
    arr = np.asarray(closes, dtype=float)
    for period, key in [(5, "sma_5"), (10, "sma_10"), (20, "sma_20"), (50, "sma_50")]:
        record[key] = float(arr[-period:].mean()) if len(arr) >= period else None

    record["ema_12"] = _ema(closes, 12)
    record["ema_26"] = _ema(closes, 26)
    record["rsi_14"] = _rsi(closes, 14)

    if record["ema_12"] is not None and record["ema_26"] is not None:
        macd_line = record["ema_12"] - record["ema_26"]
        record["macd_line"] = macd_line
        # Use a short history of macd lines to approximate the 9-period signal; we
        # store only the last value, so in the MVP we approximate via simple
        # decayed average.
        prev = record.get("macd_signal") or macd_line
        record["macd_signal"] = prev * 0.8 + macd_line * 0.2
        record["macd_histogram"] = macd_line - record["macd_signal"]
    else:
        record["macd_line"] = record["macd_signal"] = record["macd_histogram"] = None

    if len(arr) >= 20:
        window = arr[-20:]
        mid = float(window.mean())
        std = float(window.std())
        record["bb_upper"] = mid + 2 * std
        record["bb_middle"] = mid
        record["bb_lower"] = mid - 2 * std
    else:
        record["bb_upper"] = record["bb_middle"] = record["bb_lower"] = None

    if len(highs) >= 15 and len(lows) >= 15:
        tr = np.maximum.reduce(
            [
                np.asarray(highs[-14:]) - np.asarray(lows[-14:]),
                np.abs(np.asarray(highs[-14:]) - np.asarray(closes[-15:-1])),
                np.abs(np.asarray(lows[-14:]) - np.asarray(closes[-15:-1])),
            ]
        )
        record["atr_14"] = float(tr.mean())
    else:
        record["atr_14"] = None

    vol_arr = np.asarray(volumes, dtype=float)
    record["vwap"] = float((arr * vol_arr).sum() / vol_arr.sum()) if vol_arr.sum() > 0 else None
    record["volume_sma_20"] = float(vol_arr[-20:].mean()) if len(vol_arr) >= 20 else None

    obv = 0.0
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv += volumes[i]
        elif closes[i] < closes[i - 1]:
            obv -= volumes[i]
    record["obv"] = obv

    def _lag(series: list[float], lag: int) -> float | None:
        return float(series[-lag - 1]) if len(series) > lag else None

    record["price_lag_1"] = _lag(closes, 1)
    record["price_lag_5"] = _lag(closes, 5)
    record["price_lag_10"] = _lag(closes, 10)
    record["volume_lag_1"] = _lag(volumes, 1)
    record["return_1"] = (
        (close / closes[-2] - 1.0) if len(closes) >= 2 and closes[-2] else None
    )
    record["return_5"] = (
        (close / closes[-6] - 1.0) if len(closes) >= 6 and closes[-6] else None
    )
    record["return_10"] = (
        (close / closes[-11] - 1.0) if len(closes) >= 11 and closes[-11] else None
    )
    return record


class IndicatorFunction(KeyedProcessFunction):
    def __init__(self, window_size_sec: int) -> None:
        self.window_size_sec = window_size_sec
        self._history: Deque[tuple[float, float, float, float]] | None = None
        self._state = None

    def open(self, ctx: RuntimeContext) -> None:
        desc = ListStateDescriptor("history", Types.STRING())
        self._state = ctx.get_list_state(desc)
        self._history = deque(maxlen=MAX_HISTORY)
        for raw in self._state.get():
            self._history.append(tuple(json.loads(raw)))

    def process_element(self, value, ctx):  # type: ignore[no-untyped-def]
        try:
            record = avro_decode("market_bar_v1", value)
        except Exception:  # noqa: BLE001
            logger.exception("indicator decode failed")
            return
        vt_symbol = record["vt_symbol"]
        close = float(record["close"])
        high = float(record.get("high", close))
        low = float(record.get("low", close))
        volume = float(record.get("volume", 0.0) or 0.0)
        self._history.append((close, volume, high, low))
        self._persist()

        closes = [h[0] for h in self._history]
        volumes = [h[1] for h in self._history]
        highs = [h[2] for h in self._history]
        lows = [h[3] for h in self._history]

        out = _compute_indicators(
            vt_symbol=vt_symbol,
            closes=closes,
            volumes=volumes,
            highs=highs,
            lows=lows,
            window_ns=int(record["ts_ns"]),
            window_size_sec=self.window_size_sec,
        )
        yield json.dumps(out)

    def _persist(self) -> None:
        self._state.clear()
        for row in self._history:
            self._state.add(json.dumps(list(row)))


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
    sink = (
        KafkaSink.builder()
        .set_bootstrap_servers(args.bootstrap)
        .set_record_serializer(sink_ser)
        .set_transactional_id_prefix("flink-indicators-")
        .build()
    )

    stream = env.from_source(source, WatermarkStrategy.no_watermarks(), "market-bar")
    (
        stream.map(lambda s: s.encode("latin-1"))
        .key_by(lambda payload: avro_decode("market_bar_v1", payload)["vt_symbol"])
        .process(IndicatorFunction(args.window_size))
        .sink_to(sink)
    )
    env.execute("aqp-indicator-compute")


if __name__ == "__main__":
    main()
