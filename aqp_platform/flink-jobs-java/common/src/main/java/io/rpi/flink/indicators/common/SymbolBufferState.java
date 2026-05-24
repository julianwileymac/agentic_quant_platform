package io.rpi.flink.indicators.common;

import org.apache.flink.api.common.state.ListState;
import org.apache.flink.api.common.state.ListStateDescriptor;
import org.apache.flink.api.common.state.StateTtlConfig;
import org.apache.flink.api.common.time.Time;
import org.apache.flink.api.common.typeinfo.TypeInformation;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.streaming.api.functions.KeyedProcessFunction;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;

/**
 * Keyed ring-buffer state used by every indicator job to keep the last N
 * bars for the current symbol. Inspired by
 * {@code LongRidesSolution.AlertFunction} in flink-training-master which
 * demonstrates {@code ValueState} + event-time timers; here we use
 * {@code ListState} because TA-Lib indicators need an array, not a scalar.
 *
 * <p>TTL is set to 24h so symbols that stop trading do not accumulate state
 * forever on the TaskManager.</p>
 */
public final class SymbolBufferState {

    private static final int DEFAULT_MAX = 300;
    private static final String STATE_NAME = "symbol-buffer";

    private final int maxSize;
    private ListState<MarketBar> listState;

    public SymbolBufferState(int maxSize) {
        this.maxSize = maxSize;
    }

    public SymbolBufferState() {
        this(DEFAULT_MAX);
    }

    public void initialize(KeyedProcessFunction<?, ?, ?> fn) {
        ListStateDescriptor<MarketBar> desc = new ListStateDescriptor<>(
                STATE_NAME, TypeInformation.of(MarketBar.class));
        StateTtlConfig ttl = StateTtlConfig.newBuilder(Time.hours(24))
                .setUpdateType(StateTtlConfig.UpdateType.OnCreateAndWrite)
                .cleanupInRocksdbCompactFilter(1000)
                .build();
        desc.enableTimeToLive(ttl);
        this.listState = fn.getRuntimeContext().getListState(desc);
    }

    public List<MarketBar> appendAndGet(MarketBar bar) throws Exception {
        Deque<MarketBar> deque = new ArrayDeque<>(maxSize);
        for (MarketBar existing : listState.get()) {
            deque.add(existing);
        }
        deque.add(bar);
        while (deque.size() > maxSize) {
            deque.pollFirst();
        }
        listState.update(new ArrayList<>(deque));
        return new ArrayList<>(deque);
    }

    public int maxSize() {
        return maxSize;
    }
}
