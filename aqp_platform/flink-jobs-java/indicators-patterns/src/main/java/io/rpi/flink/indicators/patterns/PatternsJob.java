package io.rpi.flink.indicators.patterns;

import io.rpi.flink.indicators.common.IndicatorPipeline;
import io.rpi.flink.indicators.common.JobCommandLine;
import io.rpi.flink.indicators.common.SinkSchemas;

public final class PatternsJob {

    private PatternsJob() {
    }

    public static void main(String[] args) throws Exception {
        JobCommandLine.Config cfg = JobCommandLine.parse(args);
        cfg.categoryLabel = "patterns";
        IndicatorPipeline.run(
                "flink-java-indicators-patterns",
                cfg,
                new PatternsIndicatorFunction(cfg.bufferSize, cfg.windowSizeSec),
                SinkSchemas.FEATURES_INDICATORS_V1);
    }
}
