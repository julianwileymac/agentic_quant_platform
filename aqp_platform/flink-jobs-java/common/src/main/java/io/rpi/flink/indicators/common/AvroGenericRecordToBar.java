package io.rpi.flink.indicators.common;

import org.apache.avro.generic.GenericRecord;
import org.apache.flink.api.common.functions.MapFunction;

/**
 * Deserializes an Avro {@link GenericRecord} (market_bar_v1) into our POJO.
 * This avoids leaking Apicurio/Avro classes into the indicator code.
 */
public final class AvroGenericRecordToBar implements MapFunction<GenericRecord, MarketBar> {

    private static final long serialVersionUID = 1L;

    @Override
    public MarketBar map(GenericRecord value) {
        MarketBar bar = new MarketBar();
        bar.ts_ns = toLong(value, "ts_ns");
        Object sym = value.get("vt_symbol");
        bar.vt_symbol = sym == null ? null : sym.toString();
        bar.open = toDouble(value, "open");
        bar.high = toDouble(value, "high");
        bar.low = toDouble(value, "low");
        bar.close = toDouble(value, "close");
        bar.volume = toDouble(value, "volume");
        bar.trade_count = (int) toLong(value, "trade_count");
        bar.vwap = toDouble(value, "vwap");
        Object ex = value.get("exchange");
        bar.exchange = ex == null ? null : ex.toString();
        bar.received_ts_ns = toLong(value, "received_ts_ns");
        return bar;
    }

    private static long toLong(GenericRecord r, String field) {
        Object v = r.get(field);
        if (v instanceof Number) {
            return ((Number) v).longValue();
        }
        return 0L;
    }

    private static double toDouble(GenericRecord r, String field) {
        Object v = r.get(field);
        if (v instanceof Number) {
            return ((Number) v).doubleValue();
        }
        return 0.0;
    }
}
