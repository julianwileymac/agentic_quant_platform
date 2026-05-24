package io.rpi.flink.indicators.common;

import java.io.Serializable;
import java.util.Objects;

/**
 * POJO mirroring the {@code market_bar_v1} Avro schema. Flink's POJO
 * serializer picks up the public fields + no-args constructor.
 *
 * <p>Field names match the Avro schema so Apicurio deserialization can map
 * {@link org.apache.avro.generic.GenericRecord} into this POJO via the
 * {@link AvroGenericRecordToBar} helper.</p>
 */
public class MarketBar implements Serializable {

    private static final long serialVersionUID = 1L;

    public long ts_ns;
    public String vt_symbol;
    public double open;
    public double high;
    public double low;
    public double close;
    public double volume;
    public int trade_count;
    public double vwap;
    public String exchange;
    public long received_ts_ns;

    public MarketBar() {
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof MarketBar)) return false;
        MarketBar that = (MarketBar) o;
        return ts_ns == that.ts_ns && Objects.equals(vt_symbol, that.vt_symbol);
    }

    @Override
    public int hashCode() {
        return Objects.hash(ts_ns, vt_symbol);
    }

    @Override
    public String toString() {
        return "MarketBar{" + vt_symbol + " @ " + ts_ns + " c=" + close + " v=" + volume + "}";
    }
}
