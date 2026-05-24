package io.rpi.flink.indicators.volatility;

import io.rpi.flink.indicators.common.IndicatorPipeline;
import io.rpi.flink.indicators.common.JobCommandLine;
import io.rpi.flink.indicators.common.SinkSchemas;

public final class VolatilityJob {

    private VolatilityJob() {
    }

    public static void main(String[] args) throws Exception {
        JobCommandLine.Config cfg = JobCommandLine.parse(args);
        cfg.categoryLabel = "volatility";
        IndicatorPipeline.run(
                "flink-java-indicators-volatility",
                cfg,
                new VolatilityIndicatorFunction(cfg.bufferSize, cfg.windowSizeSec),
                SinkSchemas.FEATURES_INDICATORS_V1);
    }
}
