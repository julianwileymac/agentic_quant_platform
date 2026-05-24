package io.rpi.flink.indicators.common;

import org.apache.flink.configuration.Configuration;
import org.apache.flink.streaming.api.functions.KeyedProcessFunction;
import org.apache.flink.util.Collector;

import java.util.List;

/**
 * Base class that handles buffer lifecycle and delegates the actual TA-Lib
 * calls to {@link #compute(String, List, IndicatorRecord)}.
 */
public abstract class IndicatorFunctionBase
        extends KeyedProcessFunction<String, MarketBar, IndicatorRecord> {

    private static final long serialVersionUID = 1L;

    protected final String category;
    private final int bufferSize;
    private final int windowSizeSec;
    protected transient SymbolBufferState buffer;

    protected IndicatorFunctionBase(String category, int bufferSize, int windowSizeSec) {
        this.category = category;
        this.bufferSize = bufferSize;
        this.windowSizeSec = windowSizeSec;
    }

    @Override
    public void open(Configuration parameters) {
        this.buffer = new SymbolBufferState(bufferSize);
        this.buffer.initialize(this);
    }

    @Override
    public void processElement(MarketBar value, Context ctx, Collector<IndicatorRecord> out) throws Exception {
        List<MarketBar> history = buffer.appendAndGet(value);
        IndicatorRecord record = new IndicatorRecord(category, value);
        record.window_size_sec = windowSizeSec;
        record.window_start_ns = value.ts_ns - windowSizeSec * 1_000_000_000L;
        compute(value.vt_symbol, history, record);
        if (!record.isEmpty()) {
            out.collect(record);
        }
    }

    /**
     * Subclasses implement the category-specific TA-Lib invocations.
     * Populate {@link IndicatorRecord#put(String, double)} for every
     * indicator that has enough history to be valid for this bar.
     */
    protected abstract void compute(String symbol, List<MarketBar> history, IndicatorRecord record);
}
