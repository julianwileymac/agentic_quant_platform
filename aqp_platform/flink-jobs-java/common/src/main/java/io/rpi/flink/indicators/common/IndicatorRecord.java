package io.rpi.flink.indicators.common;

import java.io.Serializable;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Output record written to {@code features.indicators.v1}. Each category
 * job populates only the fields it owns (the shared Avro schema uses
 * unions so missing fields are allowed as {@code null}).
 *
 * <p>Rather than generating one POJO per category, we keep a single
 * {@link Map}-based payload so new indicators can be added without
 * touching the schema for the other jobs.</p>
 */
public class IndicatorRecord implements Serializable {

    private static final long serialVersionUID = 1L;

    public long ts_ns;
    public long window_start_ns;
    public int window_size_sec;
    public String vt_symbol;
    public double close;
    public long compute_ts_ns;
    public String category;
    public Map<String, Double> values = new LinkedHashMap<>();

    public IndicatorRecord() {
    }

    public IndicatorRecord(String category, MarketBar bar) {
        this.category = category;
        this.ts_ns = bar.ts_ns;
        this.vt_symbol = bar.vt_symbol;
        this.close = bar.close;
        this.compute_ts_ns = System.nanoTime();
    }

    public void put(String name, double value) {
        if (Double.isNaN(value) || Double.isInfinite(value)) {
            return;
        }
        values.put(name, value);
    }

    public boolean isEmpty() {
        return values.isEmpty();
    }
}
