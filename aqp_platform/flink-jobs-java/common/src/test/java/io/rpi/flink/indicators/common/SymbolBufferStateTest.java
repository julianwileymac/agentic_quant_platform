package io.rpi.flink.indicators.common;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Smoke test verifying that {@link IndicatorRecord#put(String, double)}
 * filters NaNs.
 */
class SymbolBufferStateTest {

    @Test
    void nanValuesAreDropped() {
        IndicatorRecord record = new IndicatorRecord("test", new MarketBar());
        record.put("sma_5", Double.NaN);
        record.put("sma_10", 10.5);
        record.put("ema_12", Double.POSITIVE_INFINITY);
        assertThat(record.values).containsOnlyKeys("sma_10");
        assertThat(record.values).containsEntry("sma_10", 10.5);
    }
}
